"""Tests for Milestone 9: Privacy Mode, Sensitive Value Suppression, and Low-Confidence STT Fallback.

Validates:
1. Privacy mode suppresses sensitive compensation figures from spoken text ("I've put it on screen.").
2. Screen message and UI cards retain full verified data for on-screen viewing.
3. Non-sensitive metrics are spoken normally with natural phrasing.
4. Low-confidence STT inputs trigger structured clarification requests rather than arbitrary actions.
5. /api/voice/respond endpoint respects privacy_mode and confidence fields.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.chat.response_planner import HumanResponsePlanner, human_response_planner
from backend.main import app


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def auth_headers(client: TestClient):
    resp = client.post(
        "/api/dev/token",
        json={"role": "Finance", "department": "Finance"},
    )
    assert resp.status_code == 200
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_privacy_mode_suppresses_salary_from_spoken_text():
    planner = HumanResponsePlanner()
    query = "What is the annual salary of Employee 1005?"
    answer = "Employee 1005 has a current annual base salary of ₹24,00,000 (24 LPA) with a performance bonus of ₹3,00,000."

    plan = planner.plan_response(
        answer=answer,
        query=query,
        privacy_mode=True,
    )

    # Spoken response MUST NOT speak the raw numbers
    assert "₹24,00,000" not in plan.spoken_response
    assert "24 lakh" not in plan.spoken_response
    assert plan.spoken_response == "I've put it on screen."
    assert "Confidential details" in plan.screen_message
    assert plan.sensitivity == "sensitive"

    # Screen UI cards must preserve the data for visual review
    assert len(plan.ui_specs) > 0


def test_automatic_salary_detection_triggers_privacy_suppression():
    planner = HumanResponsePlanner()
    query = "Show me the compensation package for Rahul"
    answer = "Rahul's compensation is $185,000 base pay plus 15% annual target bonus."

    plan = planner.plan_response(
        answer=answer,
        query=query,
        privacy_mode=False,  # auto-detected from query and answer
    )

    assert "$185,000" not in plan.spoken_response
    assert "185 thousand" not in plan.spoken_response
    assert plan.spoken_response == "I've put it on screen."
    assert plan.sensitivity == "sensitive"


def test_normal_metrics_are_spoken_when_not_sensitive():
    planner = HumanResponsePlanner()
    query = "What was our quarterly revenue?"
    answer = "Quarterly revenue reached $4.2M, representing an 8% increase over Q1."

    plan = planner.plan_response(
        answer=answer,
        query=query,
        privacy_mode=False,
    )

    # Normal enterprise metric is spoken aloud
    assert "I've put it on screen." != plan.spoken_response
    assert "4.2 million dollars" in plan.spoken_response.lower()
    assert plan.sensitivity == "normal"


def test_low_confidence_clarification_plan():
    plan = HumanResponsePlanner.create_clarification_plan(
        query="re... rev...",
        reason="low_confidence",
    )

    assert plan.confidence_level == "low"
    assert "didn't quite catch that" in plan.spoken_response.lower()
    assert len(plan.ui_specs) == 1
    assert plan.ui_specs[0].card_type == "action_card"
    assert len(plan.suggested_actions) > 0


def test_voice_respond_endpoint_with_low_confidence(client: TestClient, auth_headers: dict[str, str]):
    resp = client.post(
        "/api/voice/respond",
        headers=auth_headers,
        json={
            "query": "uh... um...",
            "confidence": 0.42,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["confidence_level"] == "low"
    assert "didn't quite catch that" in data["spoken_text"].lower()
    assert data["capability"] == "clarification"
    assert len(data["ui_specs"]) == 1
    assert data["ui_specs"][0]["card_type"] == "action_card"


def test_voice_respond_endpoint_respects_privacy_mode(client: TestClient, auth_headers: dict[str, str]):
    resp = client.post(
        "/api/voice/respond",
        headers=auth_headers,
        json={
            "query": "What is the compensation for Rahul Patel?",
            "context_override": {"privacy_mode": True},
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["spoken_text"] == "I've put it on screen."
    assert data["sensitivity"] == "sensitive"
