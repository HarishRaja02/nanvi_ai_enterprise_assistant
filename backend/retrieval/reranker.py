from __future__ import annotations
from abc import ABC, abstractmethod
from .models import RetrievalHit


class Reranker(ABC):
    @abstractmethod
    def rerank(self, query: str, hits: list[RetrievalHit], top_k: int) -> list[RetrievalHit]:
        raise NotImplementedError


class NoOpReranker(Reranker):
    """Explicit extension point; does not claim semantic reranking."""
    def rerank(self, query, hits, top_k):
        return hits[:top_k]


class ContentRelevanceReranker(Reranker):
    """Content-first reranker that validates and ranks candidates by actual content relevance."""
    def rerank(self, query: str, hits: list[RetrievalHit], top_k: int) -> list[RetrievalHit]:
        if not hits or top_k <= 0:
            return []

        import re
        query_clean = query.strip().casefold()
        terms = [w for w in re.findall(r"\w+", query_clean) if len(w) > 1]

        scored: list[tuple[float, RetrievalHit]] = []
        for hit in hits:
            content_lower = hit.chunk.content.casefold()
            content_score = 0.0
            if len(query_clean) > 5 and query_clean in content_lower:
                content_score += 20.0

            for t in terms:
                count = content_lower.count(t)
                if count > 0:
                    content_score += min(count, 5) * 2.0

            if content_score > 0:
                total_score = content_score + 0.1 * hit.score
                scored.append((total_score, hit))
            elif not terms and hit.score > 0:
                scored.append((hit.score, hit))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [h for _, h in scored[:top_k]]
