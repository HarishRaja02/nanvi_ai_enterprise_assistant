from __future__ import annotations

import json
import pytest
from fastapi.testclient import TestClient

from backend.chat.context_engine import (
    ContextManager,
    ConversationContext,
    DocumentContext,
    EntityContext,
    PageContext,
    UserContext,
)
from backend.chat.events import (
    DocumentProgress,
    EventEnvelope,
    EventType,
    SQLProgress,
    format_sse,
    make_event,
)
from backend.chat.models import ChatRequest
from backend.chat.service import ChatService, DeterministicTestAnswerer, InMemoryConversationStore
from backend.agents.orchestrator import EnterpriseOrchestrator
from backend.security.authorization import UserAttributes
from backend.security.authorization.rbac import Role
from backend.main import app


@pytest.fixture
def test_user() -> UserAttributes:
    return UserAttributes("u-m1", "tenant-m1", "Finance", frozenset({Role.FINANCE}))


def test_conversation_context_model(test_user: UserAttributes):
    user_ctx = UserContext(
        id=test_user.user_id,
        role="Finance",
        department="Finance",
        tenant_id=test_user.tenant_id,
        permissions=["Finance"],
    )
    ctx = ConversationContext(
        session_id="sess-123",
        conversation_id="conv-123",
        user=user_ctx,
        active_page=PageContext(route="/finance", page_type="finance", title="Finance Overview"),
        active_entity=EntityContext(type="invoice", id="INV-001", name="Acme Corp Invoice"),
        active_document=DocumentContext(document_id="doc-1", filename="invoice.pdf", page=1),
        last_intent="financial_revenue",
    )

    data = ctx.model_dump()
    assert data["conversation_id"] == "conv-123"
    assert data["active_page"]["route"] == "/finance"
    assert data["active_entity"]["id"] == "INV-001"
    assert data["active_document"]["filename"] == "invoice.pdf"

    # Verify sanitized slice never leaks secrets
    slice_data = ctx.sanitized_slice()
    assert "user" not in slice_data
    assert slice_data["active_page"]["route"] == "/finance"
    assert slice_data["active_entity"]["id"] == "INV-001"
    assert slice_data["last_intent"] == "financial_revenue"


def test_context_manager_lifecycle(test_user: UserAttributes):
    mgr = ContextManager()
    ctx = mgr.get_or_create("conv-test", test_user)
    assert ctx.conversation_id == "conv-test"
    assert ctx.user.id == test_user.user_id

    # Update context
    updated = mgr.update(
        "conv-test",
        {
            "active_page": PageContext(route="/customers", page_type="customers", title="Customers"),
            "active_entity": EntityContext(type="customer", id="cust-42", name="Hooli Inc"),
        },
    )
    assert updated.active_page.route == "/customers"
    assert updated.active_entity.name == "Hooli Inc"

    # Context auto-update from interaction
    after_interact = mgr.update_from_interaction(
        conversation_id="conv-test",
        user=test_user,
        query="Show invoice",
        answer="Invoice found",
        capability="database",
        sources=[{"reference_id": "ref-1", "display_name": "Invoice 1"}],
        active_document_id="inv-1.pdf",
    )
    assert after_interact.last_intent == "database"
    assert len(after_interact.last_sources) == 1
    assert after_interact.active_document.document_id == "inv-1.pdf"


def test_event_protocol_sse_formatting():
    envelope = make_event(
        EventType.STATUS,
        {"status": DocumentProgress.SEARCHING_FILES.value, "message": "Searching company files"},
        task_id="task-001",
        request_id="req-001",
    )
    assert envelope.event == EventType.STATUS
    assert envelope.task_id == "task-001"
    assert envelope.payload["status"] == "SEARCHING_FILES"

    sse_str = envelope.to_sse()
    assert sse_str.startswith("event: status\ndata: ")
    assert sse_str.endswith("\n\n")

    # Parse data JSON from SSE string
    data_line = sse_str.splitlines()[1]
    assert data_line.startswith("data: ")
    parsed = json.loads(data_line[6:])
    assert parsed["event"] == "status"
    assert parsed["task_id"] == "task-001"
    assert parsed["payload"]["message"] == "Searching company files"


def test_chat_service_stream_ask(test_user: UserAttributes):
    orchestrator = EnterpriseOrchestrator()
    answerer = DeterministicTestAnswerer()
    store = InMemoryConversationStore()
    service = ChatService(orchestrator, answerer, store)

    req = ChatRequest("Hello Nanvi", "conv-stream-1", rag_enabled=True)
    events = list(service.stream_ask(test_user, req))

    assert len(events) >= 3
    event_names = []
    for raw in events:
        lines = raw.strip().splitlines()
        for l in lines:
            if l.startswith("data: "):
                payload = json.loads(l[6:])
                event_names.append(payload["event"])

    assert "task_started" in event_names
    assert "status" in event_names
    assert "assistant_text" in event_names
    assert "task_complete" in event_names

    # Verify conversation context was stored
    ctx = service.get_context("conv-stream-1", test_user)
    assert ctx.conversation_id == "conv-stream-1"


def test_api_chat_stream_and_context_endpoints():
    client = TestClient(app)
    # Get dev token
    token_resp = client.post("/api/dev/token", json={"username": "finance", "password": "finance@nanvi"})
    assert token_resp.status_code == 200
    token = token_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Test POST /api/chat/stream
    stream_resp = client.post(
        "/api/chat/stream",
        json={"query": "Hello Nanvi", "conversation_id": "test-stream-endpoint"},
        headers=headers,
    )
    assert stream_resp.status_code == 200
    assert "text/event-stream" in stream_resp.headers["content-type"]
    text = stream_resp.text
    assert "event: task_started" in text
    assert "event: task_complete" in text

    # 2. Test GET /api/chat/context/{conversation_id}
    ctx_resp = client.get("/api/chat/context/test-stream-endpoint", headers=headers)
    assert ctx_resp.status_code == 200
    ctx_data = ctx_resp.json()
    assert ctx_data["conversation_id"] == "test-stream-endpoint"
    assert ctx_data["user"]["role"] == "Finance"

    # 3. Test PUT /api/chat/context/{conversation_id}
    update_resp = client.put(
        "/api/chat/context/test-stream-endpoint",
        json={
            "active_page": {"route": "/invoices", "page_type": "invoices", "title": "Invoices"},
            "active_entity": {"type": "invoice", "id": "INV-2026-99", "name": "Annual Service"},
        },
        headers=headers,
    )
    assert update_resp.status_code == 200
    updated_data = update_resp.json()
    assert updated_data["active_page"]["route"] == "/invoices"
    assert updated_data["active_entity"]["id"] == "INV-2026-99"
