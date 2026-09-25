from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock

import httpx
import pytest

from backend.core.resilience import RetryPolicy, retry_idempotent, DependencyTimeout
from backend.jobs import InMemoryJobQueue, JobWorker
from backend.integrations.email.graph import MicrosoftGraphEmailProvider
from backend.integrations.email.models import EmailProviderContext, EmailSearchRequest
from backend.integrations.email.exceptions import EmailProviderError
from backend.integrations.database.models import QueryRequest
from backend.integrations.database.postgres import PostgreSQLRepository
from backend.documents import DocumentProcessingService, TextParser
from backend.retrieval import KnowledgeRetrievalService, KeywordRetriever, NoOpReranker
from backend.retrieval.models import SourceMetadata, RetrievalRequest
from backend.retrieval.vector_store import InMemoryVectorStore
from backend.security.audit import AuditLogger, InMemoryAuditSink
from backend.security.authorization import AuthorizationService, UserAttributes
from backend.security.authorization.rbac import Role
from backend.reports.service import ReportService
from backend.reports.models import ReportRequest, ReportFormat
from backend.reports.storage import ReportStorage, ReportNotFound

USER = UserAttributes("u1", "t1", "Engineering", frozenset({Role.EMPLOYEE}))
CTX = EmailProviderContext("u1", "t1", "opaque-token", frozenset({"Mail.Read"}))


def test_retry_idempotent_recovers_transient_failure_without_retrying_permanent_error():
    calls = []
    def operation():
        calls.append(1)
        if len(calls) == 1:
            raise ConnectionError("temporary")
        return "ok"
    assert retry_idempotent(operation, policy=RetryPolicy(attempts=2, base_delay_seconds=0),
                            retry_if=lambda e: isinstance(e, ConnectionError)) == "ok"
    assert len(calls) == 2


def test_retry_does_not_retry_non_idempotent_classified_error():
    calls = []
    def operation():
        calls.append(1)
        raise ValueError("bad")
    with pytest.raises(ValueError):
        retry_idempotent(operation, policy=RetryPolicy(attempts=3, base_delay_seconds=0), retry_if=lambda e: False)
    assert len(calls) == 1


def test_database_retries_transient_connection_failure():
    repo = object.__new__(PostgreSQLRepository)
    repo._retry_policy = RetryPolicy(attempts=2, base_delay_seconds=0)
    repo._timeout_ms = 5_000
    repo._max_rows = 500
    repo._max_result_bytes = 2_000_000
    class OperationalError(Exception): pass
    class FakePool:
        def __init__(self): self.calls = 0
        def connection(self):
            self.calls += 1
            raise OperationalError("down")
    repo._pool = FakePool()
    with pytest.raises(OperationalError):
        repo.execute_read(QueryRequest("SELECT 1", ()))
    assert repo._pool.calls == 2


def test_email_timeout_recovers_once_then_returns_data():
    class Client:
        def __init__(self): self.calls = 0
        def get(self, *args, **kwargs):
            self.calls += 1
            if self.calls == 1: raise httpx.ReadTimeout("timeout")
            return httpx.Response(200, json={"value": []})
    provider = MicrosoftGraphEmailProvider(http_client=Client(), retry_policy=RetryPolicy(attempts=2, base_delay_seconds=0))
    page = provider.search_page(CTX, EmailSearchRequest())
    assert page.messages == ()


def test_email_invalid_response_is_safe_error_without_retry():
    class Client:
        def get(self, *args, **kwargs): return httpx.Response(200, content=b"not-json")
    provider = MicrosoftGraphEmailProvider(http_client=Client(), retry_policy=RetryPolicy(attempts=2, base_delay_seconds=0))
    with pytest.raises(EmailProviderError, match="invalid response"):
        provider.search_page(CTX, EmailSearchRequest())


def test_vector_failure_falls_back_to_keyword_without_bypassing_authorization():
    sink = InMemoryAuditSink()
    class BrokenVector(InMemoryVectorStore):
        def search(self, *args, **kwargs): raise RuntimeError("vector unavailable")
    class Embedding:
        def embed(self, text): return [1.0]
        def embed_many(self, texts): return [[1.0] for _ in texts]
    service = KnowledgeRetrievalService(Embedding(), BrokenVector(), KeywordRetriever(), NoOpReranker(),
                                        AuthorizationService(), AuditLogger(sink))
    from backend.retrieval.models import AccessControlMetadata
    source = SourceMetadata("file", "p1", "policy.txt", "Projects/policy.txt", access=AccessControlMetadata(tenant_id="t1", resource_type="knowledge_source"))
    service.index("Remote work policy allows flexible work.", source)
    result = service.retrieve(USER, RetrievalRequest("remote work", 3, 3))
    assert result.hits
    assert any(e.event_type == "knowledge_vector_search" and e.outcome == "error" for e in sink.events)


def test_document_failure_is_controlled():
    service = DocumentProcessingService([TextParser()])
    with pytest.raises(Exception) as exc:
        service.parse_bytes(filename="bad.pdf", relative_path="bad.pdf", data=b"broken")
    assert "bad.pdf" not in str(exc.value)


def test_worker_failure_does_not_report_success_or_retry_non_retryable():
    worker = JobWorker(max_attempts=3)
    job = InMemoryJobQueue().enqueue("report", {"x": 1})
    calls = []
    result = worker.process(job, lambda j: (calls.append(1), (_ for _ in ()).throw(ValueError("boom")))[1])
    assert not result.succeeded
    assert result.attempts == 1
    assert result.error == "Job processing failed"
    assert len(calls) == 1


def test_worker_retries_declared_transient_failure_then_succeeds():
    worker = JobWorker(max_attempts=3)
    job = InMemoryJobQueue().enqueue("report", {})
    calls = []
    def handler(_):
        calls.append(1)
        if len(calls) < 3: raise ConnectionError("temporary")
    result = worker.process(job, handler, retryable=lambda e: isinstance(e, ConnectionError))
    assert result.succeeded and result.attempts == 3


def test_gateway_timeout_is_safe_and_audited():
    from backend.agents.security_gateway import SecureToolGateway, ToolContext, ToolExecutionTimeout
    from backend.security.authorization import Permission, Resource
    import time
    sink = InMemoryAuditSink()
    gateway = SecureToolGateway(AuthorizationService(), AuditLogger(sink), execution_timeout_seconds=0.01)
    resource = Resource("r", "file", "t1")
    with pytest.raises(ToolExecutionTimeout):
        gateway.execute(ToolContext("req", USER), "knowledge", Permission.FILE_READ, resource,
                        lambda: time.sleep(0.05))
    assert any(e.event_type == "tool_execution" and e.outcome == "timeout" for e in sink.events)


def test_report_generation_failure_leaves_no_persisted_artifact(tmp_path):
    class BrokenStorage:
        def save(self, *args, **kwargs): raise OSError("storage unavailable")
        def get(self, *args): raise ReportNotFound()
        def open_path(self, *args): raise ReportNotFound()
        def issue_download_token(self, *args): raise ReportNotFound()
        def consume_download_token(self, *args): raise ReportNotFound()
    from backend.analysis.models import DataLineage
    audit = AuditLogger(InMemoryAuditSink())
    service = ReportService(BrokenStorage(), AuthorizationService(), audit)
    lineage = (DataLineage(source_type="file", source_id="r1", source_label="policy", columns=(), query=None,
                           tenant_id="t1", owner_id=None, department=None, restricted_department=None, resource_type="file"),)
    req = ReportRequest("00000000-0000-0000-0000-000000000001", "x", ReportFormat.EXCEL,
                        "u1", "t1", [{"a": 1}], lineage)
    with pytest.raises(OSError):
        service.create_report(USER, req)


def test_api_timeout_type_has_safe_public_message():
    assert str(DependencyTimeout("database timed out")) == "database timed out"


def test_redis_queue_unavailable_retries_and_returns_safe_error():
    from backend.jobs.queue import RedisJobQueue
    class FakeRedis:
        def __init__(self): self.calls = 0
        def eval(self, *args):
            self.calls += 1
            raise ConnectionError("redis secret=DO_NOT_LEAK")
    queue = object.__new__(RedisJobQueue)
    queue._client = FakeRedis()
    queue._queue_name = "nanvi:jobs"
    queue._retry_policy = RetryPolicy(attempts=2, base_delay_seconds=0)
    with pytest.raises(RuntimeError, match="temporarily unavailable") as exc:
        queue.enqueue("report", {"x": 1})
    assert "DO_NOT_LEAK" not in str(exc.value)
    assert queue._client.calls == 2


def test_malformed_tool_response_is_sanitized_without_secret_leak():
    from backend.agents.security_gateway import SecureToolGateway, ToolContext
    from backend.security.authorization import Permission, Resource
    sink = InMemoryAuditSink()
    gateway = SecureToolGateway(AuthorizationService(), AuditLogger(sink))
    result = gateway.execute(
        ToolContext("req", USER), "knowledge", Permission.FILE_READ, Resource("r", "file", "t1"),
        lambda: {"data": "password=super-secret", "path": r"C:\CompanyData\HR\salary.xlsx"},
    )
    assert result["data"] == "[REDACTED]"
    assert result["path"] == "[REDACTED]"


def test_invalid_llm_output_can_be_rejected_by_typed_output_validator():
    from backend.agents.security_gateway import SecureToolGateway, ToolContext, ToolPolicyDenied
    from backend.security.authorization import Permission, Resource
    gateway = SecureToolGateway(AuthorizationService(), AuditLogger(InMemoryAuditSink()))
    def validate(value):
        if not isinstance(value, dict) or "answer" not in value or not isinstance(value["answer"], str):
            raise ValueError("invalid model output")
        return value
    with pytest.raises(ValueError):
        gateway.execute(ToolContext("req", USER), "knowledge", Permission.FILE_READ, Resource("r", "file", "t1"),
                        lambda: {"answer": 123}, output_validator=validate)


def test_report_failure_is_logged_without_persisting_partial_file(tmp_path):
    from backend.analysis.models import DataLineage
    from backend.reports.generators import ExcelReportGenerator
    class BrokenGenerator:
        extension = "xlsx"
        def generate(self, request, path):
            path.write_bytes(b"partial")
            raise OSError("generator crashed")
    audit_sink = InMemoryAuditSink()
    storage = Mock()
    service = ReportService(storage, AuthorizationService(), AuditLogger(audit_sink))
    service._generators[ReportFormat.EXCEL] = BrokenGenerator()
    lineage = (DataLineage(source_type="file", source_id="r1", source_label="policy", columns=("a",),
                            tenant_id="t1", resource_type="file"),)
    req = ReportRequest("00000000-0000-0000-0000-000000000002", "x", ReportFormat.EXCEL, "u1", "t1", [{"a": 1}], lineage)
    with pytest.raises(OSError):
        service.create_report(USER, req)
    storage.save.assert_not_called()
