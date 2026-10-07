import os
import pytest
from starlette.testclient import TestClient

from backend.main import app
from backend.security.local_accounts import get_local_account_store
from backend.support.ticket_store import get_support_ticket_store
from backend.integrations.email.user_account_service import get_user_email_account_service


def test_ticket_store_serverless_resilience(monkeypatch):
    monkeypatch.setenv("VERCEL", "1")
    store = get_support_ticket_store()
    ticket = store.create_ticket(
        reporter_id="admin",
        reporter_name="System Admin",
        reporter_email="admin@company.com",
        reporter_role="Admin",
        category="General",
        severity="Low",
        subject="Resilience check",
        description="Verify ticket persistence on serverless",
    )
    assert ticket["id"].startswith("TICK-")
    assert isinstance(ticket["created_at"], str)

    tickets = store.list_tickets()
    assert len(tickets) >= 1
    assert any(t["id"] == ticket["id"] for t in tickets)


def test_email_disconnect_serverless_resilience(monkeypatch):
    monkeypatch.setenv("VERCEL", "1")
    service = get_user_email_account_service()
    # Disconnect should not raise OSError on read-only file system
    res = service.disconnect_account("admin")
    assert res is True


def test_api_endpoints_resilience(monkeypatch):
    monkeypatch.setenv("VERCEL", "1")
    client = TestClient(app)

    # 1. Login as admin
    login_resp = client.post("/api/auth/login", json={"username": "admin", "password": "admin@company"})
    assert login_resp.status_code == 200, login_resp.text
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 2. GET /api/admin/overview -> must be 200
    overview_resp = client.get("/api/admin/overview", headers=headers)
    assert overview_resp.status_code == 200, overview_resp.text
    data = overview_resp.json()
    assert "total_users" in data
    assert "total_tickets" in data

    # 3. GET /api/admin/tickets -> must be 200
    tickets_resp = client.get("/api/admin/tickets", headers=headers)
    assert tickets_resp.status_code == 200, tickets_resp.text
    assert isinstance(tickets_resp.json(), list)

    # 4. POST /api/support/tickets with short description -> must be 201 (not 422)
    short_ticket_resp = client.post(
        "/api/support/tickets",
        headers=headers,
        json={
            "category": "Bug",
            "severity": "Low",
            "subject": "Hi",
            "description": "Short",
        },
    )
    assert short_ticket_resp.status_code == 201, short_ticket_resp.text
    assert short_ticket_resp.json()["id"].startswith("TICK-")

    # 5. POST /api/email/disconnect -> must be 200 (not 500)
    disconnect_resp = client.post("/api/email/disconnect", headers=headers, json={})
    assert disconnect_resp.status_code == 200, disconnect_resp.text
    assert disconnect_resp.json() == {"status": "disconnected"}
