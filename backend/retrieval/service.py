from __future__ import annotations
from dataclasses import replace
from backend.documents.models import Document
import hashlib
import logging
import time

from backend.observability.logging import log_event

logger = logging.getLogger(__name__)
from backend.security.audit import AuditLogger
from backend.security.authorization import AuthorizationService, UserAttributes
from backend.sources.service import SourceReferenceService
from .authorization import RetrievalAuthorizer
from .chunking import DocumentChunker
from .embedding import EmbeddingProvider
from .keyword import KeywordRetriever
from .models import RetrievalHit, RetrievalRequest, RetrievalResult, SourceMetadata, KnowledgeChunk
from .reranker import Reranker
from .vector_store import VectorStore


class KnowledgeRetrievalService:
    """Unified retrieval orchestration for files/documents/email, with auth before return."""
    def __init__(self, embedding_provider: EmbeddingProvider | None,
                 vector_store: VectorStore | None, keyword_retriever: KeywordRetriever,
                 reranker: Reranker, authorization: AuthorizationService,
                 audit_logger: AuditLogger, chunker: DocumentChunker | None = None,
                 source_references: SourceReferenceService | None = None):
        self._embedding = embedding_provider
        self._vectors = vector_store
        self._keywords = keyword_retriever
        self._reranker = reranker
        self._authorizer = RetrievalAuthorizer(authorization)
        self._audit = audit_logger
        self._chunker = chunker or DocumentChunker()
        self._source_references = source_references

    def index(self, text: str, source: SourceMetadata) -> list[KnowledgeChunk]:
        chunks = self._chunker.chunk(text, source)
        self._index_chunks(chunks)
        return chunks

    def index_document(self, document: Document, access) -> list[KnowledgeChunk]:
        """Index a normalized document while preserving logical page/sheet locations.

        This is intentionally a thin adapter over the existing index() contract;
        it does not change retrieval/ranking behavior. Structured parser markers
        are converted into per-section SourceMetadata before chunking.
        """
        base = SourceMetadata(
            source_type=document.source.file_type,
            source_id=document.source.path,
            filename=document.source.filename,
            path=document.source.path,
            created_at=None,
            modified_at=document.metadata.modified_at,
            access=access,
            extra=document.metadata.extra,
        )
        sections = self._document_sections(document.text, document.source.file_type)
        all_chunks: list[KnowledgeChunk] = []
        if not sections:
            return self.index(document.text, base)
        for location, section_text in sections:
            source = base
            if document.source.file_type == "pdf":
                page = int(location.split(" ", 1)[1]) if location.startswith("Page ") else None
                source = replace(base, page=page, extra={**base.extra, "location": location})
            elif document.source.file_type == "xlsx":
                sheet = location.removeprefix("Sheet ")
                source = replace(base, sheet=sheet, extra={**base.extra, "location": location})
            else:
                source = replace(base, extra={**base.extra, "location": location})
            all_chunks.extend(self.index(section_text, source))
        return all_chunks

    @staticmethod
    def _document_sections(text: str, file_type: str) -> list[tuple[str, str]]:
        import re
        if file_type == "pdf":
            matches = list(re.finditer(r"(?m)^\[Page (\d+)\]\n", text))
            return [(f"Page {m.group(1)}", text[m.end():(matches[i + 1].start() if i + 1 < len(matches) else len(text))].strip())
                    for i, m in enumerate(matches)]
        if file_type == "xlsx":
            matches = list(re.finditer(r"(?m)^\[Sheet (.+?)\]\n", text))
            return [(f"Sheet {m.group(1)}", text[m.end():(matches[i + 1].start() if i + 1 < len(matches) else len(text))].strip())
                    for i, m in enumerate(matches)]
        return []

    def _index_chunks(self, chunks: list[KnowledgeChunk]) -> None:
        self._keywords.upsert(chunks)
        if self._embedding and self._vectors and chunks:
            self._vectors.upsert(chunks, self._embedding.embed_many([c.content for c in chunks]))

    def retrieve(self, user: UserAttributes, request: RetrievalRequest) -> RetrievalResult:
        started = time.perf_counter()
        if not request.query.strip():
            log_event(logger, "retrieval_completed", actor_id=user.user_id, tenant_id=user.tenant_id, returned=0, duration_ms=0.0)
            return RetrievalResult(())
        candidate_k = max(request.top_k, request.candidate_k)
        keyword_hits = self._keywords.search(request.query, candidate_k)
        vector_hits = []
        vector_failed = False
        if self._embedding and self._vectors:
            try:
                vector_hits = self._vectors.search(self._embedding.embed(request.query), candidate_k)
            except Exception as exc:
                # Vector search is an optimization, not an authorization boundary.
                # Fail closed for vector evidence and continue with the authorized
                # keyword path so a transient vector outage does not expose data.
                vector_failed = True
                self._audit.record(
                    "knowledge_vector_search", "error", user.user_id, user.tenant_id, None,
                    {"reason": type(exc).__name__, "fallback": "keyword"},
                )

        merged: dict[str, float] = {}
        chunks: dict[str, KnowledgeChunk] = {}
        keyword_scores: dict[str, float] = {}
        # Reciprocal-rank fusion keeps keyword/vector scores comparable without assuming same scale.
        for rank, hit in enumerate(keyword_hits, start=1):
            merged[hit.chunk.chunk_id] = merged.get(hit.chunk.chunk_id, 0.0) + 1.0 / (60 + rank)
            keyword_scores[hit.chunk.chunk_id] = hit.score
            chunks[hit.chunk.chunk_id] = hit.chunk
        for rank, hit in enumerate(vector_hits, start=1):
            merged[hit.chunk.chunk_id] = merged.get(hit.chunk.chunk_id, 0.0) + 1.0 / (60 + rank)
            chunks[hit.chunk.chunk_id] = hit.chunk

        # Use lexical evidence as a small deterministic tie-breaker. This avoids
        # vector-only ties when a query contains an exact source/content term
        # (for example "March revenue" or "renewal PDF") without increasing
        # candidate_k or changing the retrieval breadth.
        for chunk_id, lexical_score in keyword_scores.items():
            merged[chunk_id] += 0.01 * lexical_score
        candidates = [RetrievalHit(chunks[cid], score, "hybrid" if vector_hits else "keyword") for cid, score in merged.items()]
        candidates.sort(key=lambda x: x.score, reverse=True)

        # Authorization is applied before reranking and before any content can
        # reach the agent/LLM. This prevents restricted high-scoring chunks
        # from consuming the rerank budget and hiding an authorized relevant
        # result. The LLM never participates in this decision.
        allowed_candidates = []
        denied = 0
        for hit in candidates[:candidate_k]:
            if self._authorizer.allowed(user, hit.chunk):
                allowed_candidates.append(hit)
            else:
                denied += 1

        reranked = self._reranker.rerank(request.query, allowed_candidates, request.top_k)
        allowed_hits = reranked
        log_event(logger, "retrieval_completed", actor_id=user.user_id, tenant_id=user.tenant_id,
                  returned=min(len(allowed_hits), request.top_k), denied_candidates=denied,
                  vector_fallback=vector_failed, duration_ms=round((time.perf_counter() - started) * 1000, 2))
        self._audit.record(
            "knowledge_retrieval", "allow", user.user_id, user.tenant_id, None,
            {"query_sha256": hashlib.sha256(request.query.encode("utf-8")).hexdigest(), "returned": len(allowed_hits), "denied_candidates": denied, "vector_fallback": vector_failed},
        )
        return RetrievalResult(tuple(allowed_hits[:request.top_k]))

    def source_references(self, user: UserAttributes, request_id: str,
                          result: RetrievalResult):
        """Build frontend-safe citations from already-authorized retrieval hits."""
        if not self._source_references:
            return ()
        refs = []
        seen = set()
        for hit in result.hits:
            ref = self._source_references.from_metadata(user, request_id, hit.chunk.source)
            if ref and ref.reference_id not in seen:
                refs.append(ref)
                seen.add(ref.reference_id)
        return tuple(refs)
