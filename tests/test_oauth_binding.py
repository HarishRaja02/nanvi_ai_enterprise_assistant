"""Tests for OAuth account binding hardening:
- missing state rejected with 400
- invalid state rejected with 400
- replayed state rejected with 403
- cross-user state rejected with 403
- no fallback identity in token storage
"""
import dataclasses
import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.connections.manager import get_connection_manager
from backend.security.dependencies import get_current_user, get_optional_current_user
from backend.security.models import UserIdentity
from backend.security.authorization.rbac import Role
from backend.connections.providers.google import GoogleProvider
import backend.core.config as config_mod
import backend.connections.oauth_routes as oauth_routes_mod
import backend.connections.providers.google as google_prov_mod


def patch_settings(monkeypatch: pytest.MonkeyPatch, **kwargs):
    new_settings = dataclasses.replace(config_mod.settings, **kwargs)
    monkeypatch.setattr(config_mod, "settings", new_settings)
    for mod in (oauth_routes_mod, google_prov_mod):
        if hasattr(mod, "settings"):
            monkeypatch.setattr(mod, "settings", new_settings)
    return new_settings


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def alice_user():
    return UserIdentity(
        subject="alice-user-123",
        issuer="test",
        email="alice@company.com",
        name="Alice Engineer",
        tenant_id="enterprise-tenant",
        department="Engineering",
        roles=frozenset({Role.EMPLOYEE}),
    )


@pytest.fixture
def bob_user():
    return UserIdentity(
        subject="bob-user-456",
        issuer="test",
        email="bob@company.com",
        name="Bob Manager",
        tenant_id="enterprise-tenant",
        department="Management",
        roles=frozenset({Role.EMPLOYEE}),
    )


def test_oauth_missing_state_rejected(client):
    """Callback without state parameter must be rejected with 400."""
    response = client.get("/api/auth/google/callback?code=mock-auth-code")
    assert response.status_code == 400
    assert "Missing OAuth state" in response.json()["detail"]


def test_oauth_invalid_state_rejected(client):
    """Callback with nonexistent or forged state parameter must be rejected with 400."""
    response = client.get("/api/auth/google/callback?code=mock-auth-code&state=forged-unregistered-state")
    assert response.status_code == 400
    assert "Invalid or expired" in response.json()["detail"]


def test_oauth_replayed_state_rejected(client, monkeypatch, alice_user):
    """A single-use state must be rejected with 403 if replayed."""
    patch_settings(monkeypatch, google_client_id="test-google-id", google_client_secret="test-google-secret")

    cm = get_connection_manager()
    redirect_uri = "http://testserver/api/auth/google/callback"
    auth_url = cm.start_oauth("google", user=alice_user, redirect_uri=redirect_uri)

    # Extract state
    import urllib.parse
    parsed = urllib.parse.urlparse(auth_url)
    qs = urllib.parse.parse_qs(parsed.query)
    state = qs["state"][0]

    # Mock google provider handle_callback
    google_provider = cm._registry.get_provider("google")
    orig_handle = google_provider.handle_callback
    try:
        google_provider.handle_callback = lambda **kwargs: {
            "account_identifier": "alice@gmail.com",
            "display_name": "Google Workspace (alice@gmail.com)",
            "credentials": {
                "access_token": "mock-access-token-123",
                "refresh_token": "mock-refresh-token-456",
                "token_expires_at": 9999999999.0,
            },
            "metadata_safe": {"email": "alice@gmail.com", "name": "Alice"},
            "granted_scopes": ["gmail.readonly"],
        }

        # First callback with state succeeds (Redirect to frontend)
        resp1 = client.get(f"/api/auth/google/callback?code=valid-code&state={state}", follow_redirects=False)
        assert resp1.status_code in (302, 307)
        assert "connected=google&status=success" in resp1.headers["location"]

        # Second callback with the EXACT same state must be rejected with 403
        resp2 = client.get(f"/api/auth/google/callback?code=valid-code&state={state}", follow_redirects=False)
        assert resp2.status_code == 403
        assert "already been consumed" in resp2.json()["detail"]
    finally:
        google_provider.handle_callback = orig_handle


def test_oauth_cross_user_state_rejected(client, monkeypatch, alice_user, bob_user):
    """If Bob attempts to complete an OAuth callback using Alice's state, reject with 403."""
    patch_settings(monkeypatch, google_client_id="test-google-id", google_client_secret="test-google-secret")

    cm = get_connection_manager()
    redirect_uri = "http://testserver/api/auth/google/callback"
    # Alice initiates OAuth flow
    auth_url = cm.start_oauth("google", user=alice_user, redirect_uri=redirect_uri)

    import urllib.parse
    parsed = urllib.parse.urlparse(auth_url)
    qs = urllib.parse.parse_qs(parsed.query)
    alice_state = qs["state"][0]

    # Bob attempts to redeem Alice's state
    app.dependency_overrides[get_optional_current_user] = lambda: bob_user
    try:
        resp = client.get(f"/api/auth/google/callback?code=valid-code&state={alice_state}", follow_redirects=False)
        assert resp.status_code == 403
        assert "not issued to the authenticated user" in resp.json()["detail"]
    finally:
        app.dependency_overrides.pop(get_optional_current_user, None)


def test_oauth_stores_token_only_for_bound_user(client, monkeypatch, alice_user):
    """When Alice connects, tokens are stored ONLY for Alice, never for demo-ceo or dev-user-001."""
    patch_settings(monkeypatch, google_client_id="test-google-id", google_client_secret="test-google-secret")

    cm = get_connection_manager()
    redirect_uri = "http://testserver/api/auth/google/callback"
    auth_url = cm.start_oauth("google", user=alice_user, redirect_uri=redirect_uri)

    import urllib.parse
    parsed = urllib.parse.urlparse(auth_url)
    qs = urllib.parse.parse_qs(parsed.query)
    state = qs["state"][0]

    google_provider = cm._registry.get_provider("google")
    orig_handle = google_provider.handle_callback
    try:
        google_provider.handle_callback = lambda **kwargs: {
            "account_identifier": "alice@company.com",
            "display_name": "Google Workspace (alice@company.com)",
            "credentials": {
                "access_token": "alice-access-token",
                "refresh_token": "alice-refresh-token",
                "token_expires_at": 9999999999.0,
            },
            "metadata_safe": {"email": "alice@company.com", "name": "Alice"},
            "granted_scopes": ["gmail.readonly"],
        }

        resp = client.get(f"/api/auth/google/callback?code=valid-code&state={state}", follow_redirects=False)
        assert resp.status_code in (302, 307)

        # Verify connections table
        conns_alice = cm.list_connections(alice_user, provider="google")
        assert len(conns_alice) >= 1
        assert all(c.owner_user_id == alice_user.subject for c in conns_alice)
        assert any(c.account_identifier == "alice@company.com" for c in conns_alice)

        # Verify demo-ceo and dev-user-001 do NOT receive Alice's token
        demo_ceo_user = UserIdentity(
            subject="demo-ceo",
            issuer="test",
            roles=frozenset({Role.EMPLOYEE}),
            tenant_id="enterprise-tenant",
        )
        dev_user_001 = UserIdentity(
            subject="dev-user-001",
            issuer="test",
            roles=frozenset({Role.EMPLOYEE}),
            tenant_id="enterprise-tenant",
        )
        conns_ceo = cm.list_connections(demo_ceo_user, provider="google")
        conns_dev = cm.list_connections(dev_user_001, provider="google")
        assert not any(c.account_identifier == "alice@company.com" for c in conns_ceo)
        assert not any(c.account_identifier == "alice@company.com" for c in conns_dev)
    finally:
        google_provider.handle_callback = orig_handle
