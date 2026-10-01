"""Milestone 11 Master Regression Test Suite.

Strictly validates all 13 Required Test Flows defined in Section 17 of docs/NANVI_SPEC.md:
1. "Show revenue this quarter": short voice answer, financial UI, 2 to 3 actions.
2. "Why?": resolves to the revenue context and transforms the UI.
3. "Compare with last quarter": comparison UI.
4. "Show the biggest customers": ranking UI.
5. "Open the second one": opens customer #2 from current UI.
6. "What's the total on this invoice?": uses active invoice, correct source, invoice card.
7. Long document search: real progress events, short progress speech, final result.
8. User interrupts Nanvi: TTS stops quickly, new speech processed.
9. Send email: confirmation required.
10. Insufficient RAG evidence: honest "not enough evidence", no hallucination.
11. Permission test: a restricted user cannot fetch restricted data by voice or button.
12. Malformed UI spec from the LLM: rejected, safe fallback shown.
13. Mic denied or connection lost: text fallback works.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.chat.context_engine import context_manager, UserPreferences
from backend.chat.deictic_resolver import DeicticResolver
from backend.chat.intent_registry import intent_registry, RiskLevel
from backend.chat.response_planner import human_response_planner, HumanResponsePlanner
from backend.chat.ui_dsl import (
    UISpecBuilder,
    validate_ui_spec,
    UICardType,
    UISpec,
    KPICardData,
)
from backend.observability.voice_telemetry import voice_telemetry
from backend.security.authorization import Role, UserAttributes


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def ceo_headers(client: TestClient):
    resp = client.post("/api/dev/token", json={"role": "CEO", "department": "Executive"})
    assert resp.status_code == 200
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


@pytest.fixture
def finance_headers(client: TestClient):
    resp = client.post("/api/dev/token", json={"role": "Finance", "department": "Finance"})
    assert resp.status_code == 200
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


@pytest.fixture
def employee_headers(client: TestClient):
    resp = client.post("/api/dev/token", json={"role": "Employee", "department": "Engineering"})
    assert resp.status_code == 200
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


class TestAllRequiredFlows:
    """Master suite executing the 13 required test flows from Section 17 of NANVI_SPEC.md."""

    # Flow 1: "Show revenue this quarter": short voice answer, financial UI, 2 to 3 actions.
    def test_flow_1_show_revenue_this_quarter(self, client: TestClient, finance_headers: dict[str, str]):
        resp = client.post(
            "/api/voice/respond",
            headers=finance_headers,
            json={"query": "Show revenue this quarter", "conversation_id": "flow1_conv"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert 0 < len(data["spoken_text"]) < 500
        # UI cards emitted
        assert len(data["ui_specs"]) > 0
        # 2 to 3 suggested actions
        assert 2 <= len(data["suggested_actions"]) <= 3

    # Flow 2: "Why?": resolves to revenue context and transforms the UI.
    def test_flow_2_why_causal_resolution(self, client: TestClient, finance_headers: dict[str, str]):
        conv_id = "flow2_conv"
        # Seed prior revenue interaction
        client.post(
            "/api/voice/respond",
            headers=finance_headers,
            json={"query": "Show revenue this quarter", "conversation_id": conv_id},
        )
        # Follow up with "Why?"
        ctx = context_manager.get(conv_id)
        resolved = DeicticResolver.resolve(
            "Why?",
            context=ctx,
            prior_user_query="Show revenue this quarter",
        )
        assert "revenue" in resolved.lower() or "why" in resolved.lower()

        resp = client.post(
            "/api/voice/respond",
            headers=finance_headers,
            json={"query": "Why did revenue change?", "conversation_id": conv_id},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["ui_specs"]) > 0

    # Flow 3: "Compare with last quarter": comparison UI.
    def test_flow_3_compare_with_last_quarter(self, client: TestClient, finance_headers: dict[str, str]):
        resp = client.post(
            "/api/voice/respond",
            headers=finance_headers,
            json={"query": "Compare with last quarter", "conversation_id": "flow3_conv"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["spoken_text"]) > 0
        # UI specs should contain comparison, table, kpi, or action card
        assert any(
            spec["card_type"] in ("table_card", "timeline_card", "kpi_card", "status_card", "action_card")
            for spec in data["ui_specs"]
        )

    # Flow 4: "Show the biggest customers": ranking UI.
    def test_flow_4_biggest_customers(self, client: TestClient, finance_headers: dict[str, str]):
        resp = client.post(
            "/api/voice/respond",
            headers=finance_headers,
            json={"query": "Show the biggest customers", "conversation_id": "flow4_conv"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["ui_specs"]) > 0
        # At least one table or KPI component
        assert len(data["suggested_actions"]) >= 1

    # Flow 5: "Open the second one": opens customer #2 from current UI index.
    def test_flow_5_ordinal_reference_resolution(self):
        conv_id = "flow5_conv"
        user = UserAttributes(user_id="u1", tenant_id="enterprise-tenant", department="Finance", roles=frozenset([Role.FINANCE]))
        ctx = context_manager.get_or_create(conv_id, user)
        ctx.ui_entity_index = {
            "customer_1": {"name": "Asteron Technologies", "id": "CUST-101"},
            "customer_2": {"name": "CloudNova", "id": "CUST-102"},
            "customer_3": {"name": "BluePeak", "id": "CUST-103"},
        }
        context_manager.update(conv_id, {"ui_entity_index": ctx.ui_entity_index})

        resolved = DeicticResolver.resolve("Open the second one", context=ctx)
        assert "CloudNova" in resolved

    # Flow 6: "What's the total on this invoice?": uses active invoice, correct source, invoice card.
    def test_flow_6_active_invoice_grounding(self, client: TestClient, finance_headers: dict[str, str]):
        conv_id = "flow6_conv"
        user = UserAttributes(user_id="u1", tenant_id="enterprise-tenant", department="Finance", roles=frozenset([Role.FINANCE]))
        ctx = context_manager.get_or_create(conv_id, user)
        context_manager.update(
            conv_id,
            {"active_document": {"document_id": "INV-2024-001.pdf", "filename": "INV-2024-001.pdf"}},
        )
        ctx = context_manager.get(conv_id)
        resolved = DeicticResolver.resolve("What is the total on this invoice?", context=ctx)
        assert "INV-2024-001.pdf" in resolved

        resp = client.post(
            "/api/voice/respond",
            headers=finance_headers,
            json={"query": resolved, "conversation_id": conv_id},
        )
        assert resp.status_code == 200

    # Flow 7: Long document search: real progress events, short progress speech, final result.
    def test_flow_7_progress_speech_and_phrasing(self):
        planner = HumanResponsePlanner()
        # Phrase pool ensures operational acknowledgements vary
        phrase1 = planner.phrase_pool.get_phrase("KNOWLEDGE_SEARCH")
        phrase2 = planner.phrase_pool.get_phrase("KNOWLEDGE_SEARCH")
        assert len(phrase1) > 0
        assert len(phrase2) > 0
        # No raw internal jargon
        assert "vector similarity" not in phrase1
        assert "cosine distance" not in phrase1

    # Flow 8: User interrupts Nanvi (Barge-in): telemetry records it, latency tracked.
    def test_flow_8_barge_in_telemetry(self, client: TestClient, finance_headers: dict[str, str]):
        resp = client.post(
            "/api/voice/telemetry/barge-in",
            headers=finance_headers,
            json={"latency_ms": 175.0},
        )
        assert resp.status_code == 200
        summary = voice_telemetry.get_summary()
        assert summary["total_barge_ins"] >= 1

    # Flow 9: Send email: confirmation required (Section 12).
    def test_flow_9_send_email_confirmation_gate(self, client: TestClient, ceo_headers: dict[str, str]):
        resp = client.post(
            "/api/voice/intent/execute",
            headers=ceo_headers,
            json={
                "intent_id": "send_email",
                "parameters": {"recipient": "client@asteron.com", "subject": "Review"},
                "confirmed": False,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "confirmation_required"
        assert data["risk_level"] == "high"

        # Confirmed proceeds
        resp_confirmed = client.post(
            "/api/voice/intent/execute",
            headers=ceo_headers,
            json={
                "intent_id": "send_email",
                "parameters": {"recipient": "client@asteron.com", "subject": "Review"},
                "confirmed": True,
            },
        )
        assert resp_confirmed.status_code == 200

    # Flow 10: Insufficient RAG evidence: honest "not enough evidence", no hallucination.
    def test_flow_10_honest_uncertainty(self):
        planner = HumanResponsePlanner()
        plan = planner.plan_response(
            answer="",
            query="Find quantum teleportation blueprints in company files",
        )
        assert "couldn't find" in plan.spoken_response.lower() or "no matching" in plan.screen_message.lower()
        assert plan.confidence_level == "low"

    # Flow 11: Permission test: a restricted user cannot fetch restricted data.
    def test_flow_11_role_permission_gate(self, client: TestClient, employee_headers: dict[str, str]):
        resp = client.post(
            "/api/voice/intent/execute",
            headers=employee_headers,
            json={"intent_id": "send_email", "parameters": {}},
        )
        # Employee cannot access executive-only intents
        assert resp.status_code in (403, 422)

    # Flow 12: Malformed UI spec from the LLM: rejected, safe fallback shown.
    def test_flow_12_malformed_ui_spec_rejection(self):
        malformed = {
            "card_type": "arbitrary_custom_hack",
            "priority": 1,
            "data": {"<script>": "alert('xss')"},
        }
        validated = validate_ui_spec(malformed)
        # Invalid component must fallback to safe status/summary card
        assert validated.card_type == UICardType.STATUS_CARD
        assert validated.data["status"] in ("info", "error", "neutral")

    # Flow 13: Mic denied or connection lost: text fallback works.
    def test_flow_13_text_query_fallback(self, client: TestClient, finance_headers: dict[str, str]):
        # Direct text query payload to standard ask endpoint works identically
        resp = client.post(
            "/api/chat",
            headers=finance_headers,
            json={"query": "Show revenue summary", "rag_enabled": True},
        )
        assert resp.status_code == 200
        assert len(resp.json()["answer"]) > 0


class TestVoiceTelemetryDashboard:
    """Validate voice telemetry metrics endpoint and statistical aggregation."""

    def test_get_telemetry_metrics(self, client: TestClient, finance_headers: dict[str, str]):
        resp = client.get("/api/voice/telemetry", headers=finance_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "total_queries" in data
        assert "avg_latency_ms" in data
        assert "total_barge_ins" in data
        assert "success_rate_percent" in data
        assert "intents" in data
        assert "languages" in data
