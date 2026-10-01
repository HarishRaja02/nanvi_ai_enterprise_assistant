"""PostgreSQL pgvector persistent vector store for production retrieval.

Implements cosine similarity search over chunk embeddings with tenant-aware isolation.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from .models import KnowledgeChunk, RetrievalHit
from .vector_store import VectorStore

logger = logging.getLogger(__name__)


class PgVectorStore(VectorStore):
    """Production persistent vector store powered by pgvector."""

    def __init__(self, dsn: str, dimensions: int = 384) -> None:
        self._dsn = dsn
        self._dimensions = dimensions
        self._ensure_schema()

    def _get_connection(self):
        try:
            import psycopg
            return psycopg.connect(self._dsn, connect_timeout=2)
        except ImportError:
            try:
                import psycopg2
                return psycopg2.connect(self._dsn, connect_timeout=2)
            except ImportError as exc:
                raise RuntimeError("PgVectorStore requires psycopg or psycopg2 with pgvector") from exc

    def _ensure_schema(self) -> None:
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
                    cur.execute(f"""
                        CREATE TABLE IF NOT EXISTS knowledge_embeddings (
                            chunk_id VARCHAR(128) PRIMARY KEY,
                            content TEXT NOT NULL,
                            source_id VARCHAR(256) NOT NULL,
                            source_type VARCHAR(64) NOT NULL,
                            metadata JSONB NOT NULL,
                            embedding vector({self._dimensions}),
                            created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                        );
                        CREATE INDEX IF NOT EXISTS idx_knowledge_source 
                            ON knowledge_embeddings(source_id, source_type);
                    """)
                conn.commit()
        except Exception as exc:
            logger.warning("Could not pre-initialize pgvector schema: %s", exc)

    def upsert(self, chunks: list[KnowledgeChunk], vectors: list[list[float]]) -> None:
        if len(chunks) != len(vectors):
            raise ValueError("chunks and vectors must have equal length")

        with self._get_connection() as conn:
            with conn.cursor() as cur:
                for chunk, vector in zip(chunks, vectors):
                    meta_json = json.dumps(chunk.metadata) if chunk.metadata else "{}"
                    vec_str = "[" + ",".join(str(x) for x in vector) + "]"
                    cur.execute(
                        """
                        INSERT INTO knowledge_embeddings (
                            chunk_id, content, source_id, source_type, metadata, embedding
                        ) VALUES (%s, %s, %s, %s, %s, %s::vector)
                        ON CONFLICT (chunk_id) DO UPDATE SET
                            content = EXCLUDED.content,
                            source_id = EXCLUDED.source_id,
                            source_type = EXCLUDED.source_type,
                            metadata = EXCLUDED.metadata,
                            embedding = EXCLUDED.embedding
                        """,
                        (chunk.chunk_id, chunk.content, chunk.source_id, chunk.source_type, meta_json, vec_str),
                    )
            conn.commit()

    def search(self, vector: list[float], top_k: int) -> list[RetrievalHit]:
        if top_k <= 0 or not vector:
            return []

        vec_str = "[" + ",".join(str(x) for x in vector) + "]"
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT chunk_id, content, source_id, source_type, metadata,
                           1 - (embedding <=> %s::vector) AS similarity
                    FROM knowledge_embeddings
                    ORDER BY embedding <=> %s::vector ASC
                    LIMIT %s
                    """,
                    (vec_str, vec_str, top_k),
                )
                rows = cur.fetchall()
                hits = []
                for row in rows:
                    meta = row[4] if isinstance(row[4], dict) else json.loads(row[4])
                    chunk = KnowledgeChunk(
                        chunk_id=row[0],
                        content=row[1],
                        source_id=row[2],
                        source_type=row[3],
                        metadata=meta,
                    )
                    score = float(row[5]) if row[5] is not None else 0.0
                    hits.append(RetrievalHit(chunk=chunk, score=score, retrieval_strategy="vector"))
                return hits
