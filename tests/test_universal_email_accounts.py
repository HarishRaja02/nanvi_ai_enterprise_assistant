"""Tests for Universal Email / Google OAuth multi-user mailbox storage and endpoints."""
import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.core.config import settings
from backend.integrations.email.user_account_service import (
    UserEmailAccount,
    get_user_email_account_service,
)


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def auth_header(client):
    resp = client.post("/api/dev/token", json={"role": "CEO", "name": "Arjun Mehta", "email": "ceo@nanvi.local"})
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_user_email_account_service_crud():
    svc = get_user_email_account_service()
    account = UserEmailAccount(
        id="test-acc-001",
        user_id="user-universal-1",
        email_address="universal.employee@company.com",
        display_name="Universal Employee",
        provider="google",
        access_token="test_access_token",
        refresh_token="test_refresh_token",
        token_expires_at=9999999999.0,
    )
    saved = svc.save_account(account)
    assert saved.email_address == "universal.employee@company.com"

    fetched = svc.get_active_account("user-universal-1")
    assert fetched is not None
    assert fetched.email_address == "universal.employee@company.com"

    # Disconnect
    svc.disconnect_account("user-universal-1", "test-acc-001")
    active = svc.get_active_account("user-universal-1")
    assert active is None


def test_mailbox_status_endpoint(client, auth_header):
    resp = client.get("/api/email/status", headers=auth_header)
    assert resp.status_code == 200
    data = resp.json()
    assert "connected" in data


def test_google_auth_url_endpoint(client, auth_header):
    resp = client.get("/api/email/oauth/google/url", headers=auth_header)
    assert resp.status_code == 200
    data = resp.json()
    assert "auth_url" in data
    assert "accounts.google.com" in data["auth_url"]
    assert "gmail.readonly" in data["auth_url"]


def test_manual_connect_and_disconnect(client, auth_header):
    # Connect
    conn_resp = client.post(
        "/api/email/manual-connect",
        json={"email_address": "test.user@nanvi.com", "display_name": "Test User"},
        headers=auth_header,
    )
    assert conn_resp.status_code == 200
    assert conn_resp.json()["account"]["email_address"] == "test.user@nanvi.com"

    # Status shows connected
    st_resp = client.get("/api/email/status", headers=auth_header)
    assert st_resp.status_code == 200
    assert st_resp.json()["connected"] is True
    assert st_resp.json()["account"]["email_address"] == "test.user@nanvi.com"

    # Disconnect
    disc_resp = client.post("/api/email/disconnect", headers=auth_header)
    assert disc_resp.status_code == 200

    # Status shows disconnected
    st_resp2 = client.get("/api/email/status", headers=auth_header)
    assert st_resp2.status_code == 200
    assert st_resp2.json()["connected"] is False
