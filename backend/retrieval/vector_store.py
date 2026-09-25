from __future__ import annotations
from abc import ABC, abstractmethod
import math
from heapq import nlargest
from .models import KnowledgeChunk, RetrievalHit


class VectorStore(ABC):
    @abstractmethod
    def upsert(self, chunks: list[KnowledgeChunk], vectors: list[list[float]]) -> None:
        raise NotImplementedError

    @abstractmethod
    def search(self, vector: list[float], top_k: int) -> list[RetrievalHit]:
        raise NotImplementedError


class InMemoryVectorStore(VectorStore):
    """Small reference implementation for development/tests; replaceable by pgvector/Qdrant/etc."""

    def __init__(self):
        self._items: dict[str, tuple[KnowledgeChunk, tuple[float, ...]]] = {}

    def upsert(self, chunks, vectors):
        if len(chunks) != len(vectors):
            raise ValueError("chunks and vectors must have equal length")
        for chunk, vector in zip(chunks, vectors):
            normalized = _normalize(vector)
            self._items[chunk.chunk_id] = (chunk, normalized)

    def search(self, vector, top_k):
        if top_k <= 0:
            return []
        query = _normalize(vector)
        if not query:
            return []
        scored = []
        for chunk, candidate in self._items.values():
            if len(query) != len(candidate):
                continue
            score = sum(x * y for x, y in zip(query, candidate))
            # Zero-similarity items carry no semantic evidence and should not
            # consume candidate slots.
            if score > 0.0:
                scored.append((score, chunk.chunk_id, chunk))
        best = nlargest(top_k, scored, key=lambda item: (item[0], item[1]))
        return [RetrievalHit(chunk, score, "vector") for score, _, chunk in best]


def _normalize(vector: list[float] | tuple[float, ...]) -> tuple[float, ...]:
    if not vector:
        return ()
    norm = math.sqrt(sum(x * x for x in vector))
    if not norm:
        return ()
    return tuple(x / norm for x in vector)
