from __future__ import annotations

import io
import json
import logging
import time

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.observability.logging import (
    JsonFormatter,
    get_correlation_id,
    get_request_id,
    get_trace_id,
    log_event,
    reset_request_context,
    sanitize,
    set_request_context,
)
from backend.observability.middleware import RequestContextMiddleware
from backend.security.audit import AuditLogger, InMemoryAuditSink


def test_structured_log_contains_trace_correlation_and_request_ids_without_secret():
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    logger = logging.getLogger("test.observability")
    logger.handlers.clear()
    logger.propagate = False
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)
    tokens = set_request_context("req-123", "corr-456", "trace-789")
    try:
        log_event(logger, "sample_event", actor_id="user-1", password="super-secret", query="salary report")
    finally:
        reset_request_context(tokens)
        logger.removeHandler(handler)
    record = json.loads(stream.getvalue())
    assert record["event"] == "sample_event"
    assert record["request_id"] == "req-123"
    assert record["correlation_id"] == "corr-456"
    assert record["trace_id"] == "trace-789"
    assert record["password"] == "[REDACTED]"
    assert "super-secret" not in stream.getvalue()
    assert "salary report" in stream.getvalue()


def test_sanitize_redacts_bearer_token_and_secret_assignments():
    value = sanitize({
        "authorization": "Bearer abc.def.ghi",
        "api_key": "abc123",
        "nested": "access_token=secret-token",
        "safe_count": 4,
    })
    assert value["authorization"] == "[REDACTED]"
    assert value["api_key"] == "[REDACTED]"
    assert value["nested"] == "access_token=[REDACTED]"
    assert value["safe_count"] == 4


def test_request_context_middleware_propagates_headers_and_logs_latency():
    app = FastAPI()
    app.add_middleware(RequestContextMiddleware)

    @app.get("/work")
    async def work():
        time.sleep(0.001)
        return {"ok": True}

    client = TestClient(app)
    response = client.get("/work", headers={"X-Request-ID": "req-client", "X-Correlation-ID": "corr-client"})
    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "req-client"
    assert response.headers["X-Correlation-ID"] == "corr-client"
    assert len(response.headers["X-Trace-ID"]) == 32
    assert float(response.headers["X-Response-Time-Ms"]) >= 0


def test_invalid_context_headers_are_replaced():
    app = FastAPI()
    app.add_middleware(RequestContextMiddleware)

    @app.get("/")
    async def root():
        return {"ok": True}

    response = TestClient(app).get("/", headers={"X-Request-ID": "bad value", "X-Correlation-ID": "x" * 129})
    assert response.status_code == 200
    assert response.headers["X-Request-ID"] != "bad value"
    assert response.headers["X-Correlation-ID"] != "x" * 129


def test_audit_event_contains_investigation_context_and_scrubbed_metadata():
    sink = InMemoryAuditSink()
    audit = AuditLogger(sink)
    tokens = set_request_context("req-a", "corr-a", "trace-a")
    try:
        audit.record(
            "security_test", "deny", "user-a", "tenant-a", "resource-a",
            {"reason": "policy", "password": "do-not-store", "attempts": 2},
        )
    finally:
        reset_request_context(tokens)
    event = sink.events[0]
    assert event.request_id == "req-a"
    assert event.correlation_id == "corr-a"
    assert event.trace_id == "trace-a"
    assert event.metadata["password"] == "[REDACTED]"
    assert event.metadata["attempts"] == 2
    assert event.actor_id == "user-a"
    assert event.tenant_id == "tenant-a"
    assert event.resource_id == "resource-a"
