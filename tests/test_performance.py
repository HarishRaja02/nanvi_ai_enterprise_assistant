from __future__ import annotations

import time

from backend.retrieval.embedding import EmbeddingProvider
from backend.retrieval.keyword import KeywordRetriever
from backend.retrieval.models import AccessControlMetadata, RetrievalRequest, SourceMetadata
from backend.retrieval.reranker import NoOpReranker
from backend.retrieval.service import KnowledgeRetrievalService
from backend.retrieval.vector_store import InMemoryVectorStore
from backend.security.audit import AuditLogger, InMemoryAuditSink
from backend.security.authorization import AuthorizationService, UserAttributes
from backend.security.authorization.rbac import Role


class TestEmbedding(EmbeddingProvider):
    def embed(self, text: str) -> list[float]:
        vector = [0.0] * 32
        for token in text.lower().split():
            vector[hash(token) % 32] += 1.0
        return vector


def _service_with_5k_chunks():
    service = KnowledgeRetrievalService(
        TestEmbedding(), InMemoryVectorStore(), KeywordRetriever(), NoOpReranker(),
        AuthorizationService(), AuditLogger(InMemoryAuditSink())
    )
    access = AccessControlMetadata("tenant-1", department="Engineering")
    for i in range(5000):
        service.index(
            f"project atlas roadmap launch milestone record {i}",
            SourceMetadata("txt", f"source-{i}", f"doc{i}.txt", f"Projects/doc{i}.txt", access=access),
        )
    return service


def test_retrieval_performance_regression_budget():
    service = _service_with_5k_chunks()
    user = UserAttributes("user-1", "tenant-1", "Engineering", frozenset({Role.EMPLOYEE}))
    started = time.perf_counter()
    result = service.retrieve(user, RetrievalRequest("atlas roadmap milestone", 10, 30))
    elapsed_ms = (time.perf_counter() - started) * 1000
    assert result.hits
    assert len(result.hits) <= 10
    assert elapsed_ms < 250


def test_retrieval_repeated_question_performance_budget():
    service = _service_with_5k_chunks()
    user = UserAttributes("user-1", "tenant-1", "Engineering", frozenset({Role.EMPLOYEE}))
    request = RetrievalRequest("atlas roadmap milestone", 10, 30)
    started = time.perf_counter()
    for _ in range(10):
        assert service.retrieve(user, request).hits
    elapsed_ms = (time.perf_counter() - started) * 1000
    assert elapsed_ms < 2500
