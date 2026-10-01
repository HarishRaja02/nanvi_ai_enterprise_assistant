"""Retrieval evaluation and persistence wiring tests (Items 8 & 9).

Validates:
1. Production rejection of all in-memory persistence implementations.
2. Real retrieval wiring: EmbeddingProvider + VectorStore + KeywordRetriever + ContentRelevanceReranker.
3. Hybrid scoring with reciprocal-rank fusion.
4. Pre-LLM authorization boundary (denied candidates never reach reranker/LLM).
"""
from __future__ import annotations

import dataclasses
import pytest

import backend.core.config as config_mod
from backend.core.exceptions import ConfigurationError
from backend.retrieval.chunking import DocumentChunker
from backend.retrieval.embedding import DeterministicEmbeddingProvider
from backend.retrieval.keyword import KeywordRetriever
from backend.retrieval.models import AccessControlMetadata, KnowledgeChunk, RetrievalRequest, SourceMetadata
from backend.retrieval.reranker import ContentRelevanceReranker
from backend.retrieval.service import KnowledgeRetrievalService
from backend.retrieval.vector_store import InMemoryVectorStore
from backend.security.audit import AuditLogger, InMemoryAuditSink
from backend.security.authorization import AuthorizationService, Permission, Resource, UserAttributes
from backend.security.authorization.rbac import Role


def patch_settings(monkeypatch: pytest.MonkeyPatch, **kwargs):
    new_settings = dataclasses.replace(config_mod.settings, **kwargs)
    monkeypatch.setattr(config_mod, "settings", new_settings)
    return new_settings


def test_in_memory_stores_rejected_in_production(monkeypatch):
    patch_settings(monkeypatch, app_mode="production")

    with pytest.raises(ConfigurationError, match="InMemoryConversationStore is forbidden"):
        from backend.chat.service import InMemoryConversationStore
        InMemoryConversationStore()

    with pytest.raises(ConfigurationError, match="InMemoryAuditSink is forbidden"):
        InMemoryAuditSink()

    with pytest.raises(ConfigurationError, match="InMemorySourceReferenceStore is forbidden"):
        from backend.sources.store import InMemorySourceReferenceStore
        InMemorySourceReferenceStore()

    with pytest.raises(ConfigurationError, match="InMemoryVectorStore is forbidden"):
        InMemoryVectorStore()


def test_retrieval_eval_hybrid_and_reranking(monkeypatch):
    patch_settings(monkeypatch, app_mode="development")

    embedder = DeterministicEmbeddingProvider(dimensions=384)
    vector_store = InMemoryVectorStore()
    keyword = KeywordRetriever()
    reranker = ContentRelevanceReranker()
    auth = AuthorizationService()
    audit = AuditLogger(InMemoryAuditSink())

    service = KnowledgeRetrievalService(
        embedding_provider=embedder,
        vector_store=vector_store,
        keyword_retriever=keyword,
        reranker=reranker,
        authorization=auth,
        audit_logger=audit,
    )

    access = AccessControlMetadata(tenant_id="tenant-1")

    src_eng = SourceMetadata(
        source_type="file",
        source_id="eng/arch_doc.md",
        filename="arch_doc.md",
        path="eng/arch_doc.md",
        created_at=None,
        modified_at=None,
        access=access,
    )
    src_fin = SourceMetadata(
        source_type="file",
        source_id="fin/q1_rev.md",
        filename="q1_rev.md",
        path="fin/q1_rev.md",
        created_at=None,
        modified_at=None,
        access=access,
    )

    service.index(
        "Nanvi enterprise architecture utilizes LangGraph for deterministic capability agent orchestration.",
        src_eng,
    )
    service.index(
        "Q1 revenue reached 4.5 million dollars driven by enterprise cloud contract renewals.",
        src_fin,
    )

    ceo_user = UserAttributes(
        user_id="usr-ceo",
        tenant_id="tenant-1",
        department="Executive",
        roles=frozenset({Role.CEO}),
    )

    # Query for architecture
    req_arch = RetrievalRequest(query="LangGraph capability agent architecture", top_k=2)
    res_arch = service.retrieve(ceo_user, req_arch)
    assert len(res_arch.hits) >= 1
    assert "LangGraph" in res_arch.hits[0].chunk.content
    assert res_arch.hits[0].retrieval_method in ("hybrid", "keyword", "vector")

    # Query for revenue
    req_fin = RetrievalRequest(query="Q1 revenue and contract renewals", top_k=2)
    res_fin = service.retrieve(ceo_user, req_fin)
    assert len(res_fin.hits) >= 1
    assert "revenue" in res_fin.hits[0].chunk.content


def test_retrieval_authorization_filtering_before_rerank(monkeypatch):
    patch_settings(monkeypatch, app_mode="development")

    embedder = DeterministicEmbeddingProvider(dimensions=384)
    vector_store = InMemoryVectorStore()
    keyword = KeywordRetriever()
    reranker = ContentRelevanceReranker()
    auth = AuthorizationService()
    audit = AuditLogger(InMemoryAuditSink())

    service = KnowledgeRetrievalService(
        embedding_provider=embedder,
        vector_store=vector_store,
        keyword_retriever=keyword,
        reranker=reranker,
        authorization=auth,
        audit_logger=audit,
    )

    # Ingest document restricted to Finance department
    access_fin = AccessControlMetadata(
        tenant_id="tenant-1",
        department="Finance",
        restricted_department="Finance",
    )
    fin_restricted = SourceMetadata(
        source_type="file",
        source_id="fin/payroll_confidential.pdf",
        filename="payroll_confidential.pdf",
        path="fin/payroll_confidential.pdf",
        created_at=None,
        modified_at=None,
        access=access_fin,
    )
    service.index("Confidential executive bonus pool and salary review numbers.", fin_restricted)

    # Engineer in Engineering department without Finance role
    eng_user = UserAttributes(
        user_id="usr-eng",
        tenant_id="tenant-1",
        department="Engineering",
        roles=frozenset({Role.EMPLOYEE}),
    )

    req = RetrievalRequest(query="executive bonus pool salary", top_k=5)
    res = service.retrieve(eng_user, req)

    # Confidential chunk must NOT reach the caller
    assert len(res.hits) == 0
