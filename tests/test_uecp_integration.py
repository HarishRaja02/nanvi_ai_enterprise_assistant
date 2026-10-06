"""Comprehensive verification suite for UECP Integration.

Validates all 10 core security invariants:
1. Successful validation -> ALLOW
2. Frozen credential -> DENY
3. Expired credential -> DENY
4. Revoked credential -> DENY
5. Parent frozen -> DENY
6. Unfreezing parent -> ALLOW
7. UECP unavailable/timeout -> FAIL CLOSED (503)
8. Invalid/malformed UECP response -> FAIL CLOSED
9. Validation cache TTL and rapid invalidation
10. Missing permission / entitlement -> DENY
11. Secret protection (no secret in logs, bundles, responses, repr)
12. Health endpoints safe inspection
"""
from __future__ import annotations

import io
import json
import logging
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest
from fastapi import FastAPI, Depends
from fastapi.testclient import TestClient

from backend.security.authorization.rbac import Role
from backend.security.dependencies import get_current_user
from backend.security.models import UserIdentity
from backend.uecp.authorization import UECPAuthorizationService
from backend.uecp.cache import UECPValidationCache
from backend.uecp.client import UECPClient
from backend.uecp.config import UECPConfig
from backend.uecp.exceptions import (
    UECPAccessDenied,
    UECPCredentialExpired,
    UECPCredentialFrozen,
    UECPCredentialRevoked,
    UECPInvalidResponse,
    UECPParentFrozen,
    UECPUnauthorized,
    UECPUnavailable,
)
from backend.uecp.middleware import require_uecp_access
from backend.uecp.models import UECPAccessState


@pytest.fixture
def dummy_user() -> UserIdentity:
    return UserIdentity(
        subject="usr-001",
        issuer="nanvi",
        email="operator@enterprise.com",
        name="Enterprise Operator",
        tenant_id="tenant-acme",
        department="Operations",
        roles=frozenset({Role.SUPERVISOR}),
    )


@pytest.fixture
def uecp_config() -> UECPConfig:
    return UECPConfig(
        enabled=True,
        base_url="https://controlplane.enterprise.internal",
        application_id="nanvi-enterprise-assistant",
        application_key="app-key-secret-12345",
        credential_id="cred-98765",
        credential_secret="CRITICAL_SECRET_VALUE_NEVER_LEAK_9999",
        validation_timeout_seconds=2.0,
        cache_ttl_seconds=60,
        allow_insecure_http=False,
    )


def create_test_app(service: UECPAuthorizationService, user: UserIdentity) -> FastAPI:
    app = FastAPI()

    @app.get("/protected/chat")
    def protected_chat(
        access: UECPAccessState = Depends(require_uecp_access(permission="ai.chat")),
    ):
        return {"status": "ok", "business_logic_executed": True, "allowed": access.allowed}

    @app.get("/protected/docs")
    def protected_docs(
        access: UECPAccessState = Depends(require_uecp_access(permission="documents.read")),
    ):
        return {"status": "ok", "docs": ["doc1.pdf"], "allowed": access.allowed}

    # Dependency overrides for isolated test execution
    from backend.uecp.authorization import get_uecp_service

    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_uecp_service] = lambda: service
    return app


# ── 1. Successful Validation ──────────────────────────────────────────────────

def test_successful_validation_allows_access(uecp_config: UECPConfig, dummy_user: UserIdentity) -> None:
    """UECP returns ALLOW -> protected endpoint executes business logic."""
    cache = UECPValidationCache(default_ttl_seconds=60)
    client = MagicMock(spec=UECPClient)
    client.validate_credential.return_value = UECPAccessState(
        allowed=True,
        reason=None,
        entitlements=("ai.chat", "documents.read"),
        organization_id="tenant-acme",
        application_id=uecp_config.application_id,
    )

    service = UECPAuthorizationService(config=uecp_config, client=client, cache=cache)
    app = create_test_app(service, dummy_user)
    tc = TestClient(app)

    response = tc.get("/protected/chat")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["business_logic_executed"] is True
    assert data["allowed"] is True


# ── 2. Frozen Credential ──────────────────────────────────────────────────────

def test_frozen_credential_denies_access(uecp_config: UECPConfig, dummy_user: UserIdentity) -> None:
    """UECP reports credential_frozen -> Nanvi blocks request (403), business logic is NOT executed."""
    client = MagicMock(spec=UECPClient)
    client.validate_credential.return_value = UECPAccessState(
        allowed=False,
        reason="credential_frozen",
        entitlements=(),
        organization_id="tenant-acme",
        status="frozen",
    )

    service = UECPAuthorizationService(config=uecp_config, client=client)
    app = create_test_app(service, dummy_user)
    tc = TestClient(app)

    response = tc.get("/protected/chat")
    assert response.status_code == 403
    data = response.json()
    assert data["detail"]["error"] == "access_denied"
    assert "Your organization's Nanvi access is currently unavailable" in data["detail"]["message"]
    # Secrets must not appear
    assert uecp_config.credential_secret not in response.text


# ── 3. Expired Credential ─────────────────────────────────────────────────────

def test_expired_credential_denies_access(uecp_config: UECPConfig, dummy_user: UserIdentity) -> None:
    """UECP reports credential_expired -> Nanvi blocks request (403)."""
    client = MagicMock(spec=UECPClient)
    client.validate_credential.return_value = UECPAccessState(
        allowed=False,
        reason="credential_expired",
        entitlements=(),
        organization_id="tenant-acme",
        status="expired",
    )

    service = UECPAuthorizationService(config=uecp_config, client=client)
    app = create_test_app(service, dummy_user)
    tc = TestClient(app)

    response = tc.get("/protected/chat")
    assert response.status_code == 403
    assert response.json()["detail"]["error"] == "access_denied"


# ── 4. Revoked Credential ─────────────────────────────────────────────────────

def test_revoked_credential_denies_access(uecp_config: UECPConfig, dummy_user: UserIdentity) -> None:
    """UECP reports credential_revoked -> Nanvi blocks request (403)."""
    client = MagicMock(spec=UECPClient)
    client.validate_credential.return_value = UECPAccessState(
        allowed=False,
        reason="credential_revoked",
        entitlements=(),
        organization_id="tenant-acme",
        status="revoked",
    )

    service = UECPAuthorizationService(config=uecp_config, client=client)
    app = create_test_app(service, dummy_user)
    tc = TestClient(app)

    response = tc.get("/protected/chat")
    assert response.status_code == 403
    assert response.json()["detail"]["error"] == "access_denied"


# ── 5. Parent Frozen (Hierarchy) ──────────────────────────────────────────────

def test_parent_frozen_blocks_descendants(uecp_config: UECPConfig, dummy_user: UserIdentity) -> None:
    """Root credential frozen -> child credential is effectively denied."""
    client = MagicMock(spec=UECPClient)
    client.validate_credential.return_value = UECPAccessState(
        allowed=False,
        reason="parent_frozen",
        entitlements=(),
        organization_id="tenant-acme",
        status="parent_frozen",
    )

    service = UECPAuthorizationService(config=uecp_config, client=client)
    app = create_test_app(service, dummy_user)
    tc = TestClient(app)

    response = tc.get("/protected/chat")
    assert response.status_code == 403
    assert response.json()["detail"]["error"] == "access_denied"


# ── 6. Unfreezing Parent Restores Access ──────────────────────────────────────

def test_unfreezing_parent_restores_access(uecp_config: UECPConfig, dummy_user: UserIdentity) -> None:
    """Unfreezing parent restores descendants unless independently frozen."""
    cache = UECPValidationCache(default_ttl_seconds=60)
    client = MagicMock(spec=UECPClient)

    # First attempt: parent is frozen
    client.validate_credential.return_value = UECPAccessState(
        allowed=False,
        reason="parent_frozen",
        organization_id="tenant-acme",
    )
    service = UECPAuthorizationService(config=uecp_config, client=client, cache=cache)
    app = create_test_app(service, dummy_user)
    tc = TestClient(app)

    resp1 = tc.get("/protected/chat")
    assert resp1.status_code == 403

    # Admin unfreezes parent: cache is invalidated, subsequent check succeeds
    cache.invalidate_organization("tenant-acme")
    client.validate_credential.return_value = UECPAccessState(
        allowed=True,
        reason=None,
        entitlements=("ai.chat",),
        organization_id="tenant-acme",
    )

    resp2 = tc.get("/protected/chat")
    assert resp2.status_code == 200
    assert resp2.json()["business_logic_executed"] is True


# ── 7. Fail-Closed on UECP Outage / Timeout ───────────────────────────────────

def test_uecp_unavailable_timeout_fails_closed(uecp_config: UECPConfig, dummy_user: UserIdentity) -> None:
    """UECP timeout or unreachable -> FAIL CLOSED (503), safe error without leaking internal details."""
    client = MagicMock(spec=UECPClient)
    client.validate_credential.side_effect = UECPUnavailable("UECP validation timed out")

    service = UECPAuthorizationService(config=uecp_config, client=client)
    app = create_test_app(service, dummy_user)
    tc = TestClient(app)

    response = tc.get("/protected/chat")
    assert response.status_code == 503
    data = response.json()
    assert data["detail"]["error"] == "service_unavailable"
    assert "temporarily unavailable" in data["detail"]["message"]
    # Internal URLs and secrets must NEVER leak
    assert uecp_config.base_url not in response.text
    assert uecp_config.credential_secret not in response.text


# ── 8. Fail-Closed on Malformed Response ───────────────────────────────────────

def test_malformed_uecp_response_fails_closed(uecp_config: UECPConfig, dummy_user: UserIdentity) -> None:
    """Malformed or non-JSON response from UECP -> FAIL CLOSED (503)."""
    client = MagicMock(spec=UECPClient)
    client.validate_credential.side_effect = UECPInvalidResponse("Corrupted payload")

    service = UECPAuthorizationService(config=uecp_config, client=client)
    app = create_test_app(service, dummy_user)
    tc = TestClient(app)

    response = tc.get("/protected/chat")
    assert response.status_code == 503
    assert response.json()["detail"]["error"] == "service_unavailable"


# ── 9. Cache TTL and Invalidation ─────────────────────────────────────────────

def test_cache_hits_and_ttl_behavior(uecp_config: UECPConfig, dummy_user: UserIdentity) -> None:
    """First request calls UECP; second request uses cache; eviction re-checks UECP."""
    cache = UECPValidationCache(default_ttl_seconds=60)
    client = MagicMock(spec=UECPClient)
    client.validate_credential.return_value = UECPAccessState(
        allowed=True,
        reason=None,
        entitlements=("ai.chat",),
        organization_id="tenant-acme",
    )

    service = UECPAuthorizationService(config=uecp_config, client=client, cache=cache)
    app = create_test_app(service, dummy_user)
    tc = TestClient(app)

    # 1. First call -> invokes client
    tc.get("/protected/chat")
    assert client.validate_credential.call_count == 1

    # 2. Second call within TTL -> served from cache
    tc.get("/protected/chat")
    assert client.validate_credential.call_count == 1

    # 3. Explicit cache invalidation -> invokes client again
    cache.invalidate("tenant-acme", "ai.chat")
    tc.get("/protected/chat")
    assert client.validate_credential.call_count == 2


# ── 10. Missing Permission / Entitlement Denies ───────────────────────────────

def test_missing_permission_entitlement_denies_access(uecp_config: UECPConfig, dummy_user: UserIdentity) -> None:
    """UECP grants documents.read but NOT ai.chat -> chat endpoint is DENIED (403)."""
    client = MagicMock(spec=UECPClient)
    client.validate_credential.return_value = UECPAccessState(
        allowed=True,
        reason=None,
        entitlements=("documents.read",),  # ai.chat is NOT granted
        organization_id="tenant-acme",
    )

    service = UECPAuthorizationService(config=uecp_config, client=client)
    app = create_test_app(service, dummy_user)
    tc = TestClient(app)

    # Calling chat should be blocked
    chat_resp = tc.get("/protected/chat")
    assert chat_resp.status_code == 403

    # Calling docs should be allowed
    docs_resp = tc.get("/protected/docs")
    assert docs_resp.status_code == 200
    assert docs_resp.json()["docs"] == ["doc1.pdf"]


# ── 11. Secret Protection Hygiene ─────────────────────────────────────────────

def test_secret_never_appears_in_logs_repr_or_bundle(uecp_config: UECPConfig) -> None:
    """Verify UECP_CREDENTIAL_SECRET never appears in repr, logs, or frontend build artifacts."""
    secret = uecp_config.credential_secret

    # 1. Config repr must mask secret
    repr_str = repr(uecp_config)
    assert secret not in repr_str
    assert "[MASKED]" in repr_str

    # 2. Structured log sanitization
    from backend.observability.logging import sanitize
    sanitized_data = sanitize({"credential_secret": secret, "api_key": "some_key"})
    assert sanitized_data["credential_secret"] == "[REDACTED]"
    assert sanitized_data["api_key"] == "[REDACTED]"

    # 3. Check frontend dist bundle if it exists
    dist_dir = Path(__file__).resolve().parent.parent / "frontend" / "dist"
    if dist_dir.exists():
        for js_file in dist_dir.glob("**/*.js"):
            content = js_file.read_text(encoding="utf-8", errors="ignore")
            assert secret not in content, f"Secret leaked in bundle: {js_file}"


# ── 12. Health Check Endpoint ─────────────────────────────────────────────────

def test_uecp_health_endpoint_safe(uecp_config: UECPConfig) -> None:
    """GET /api/health/uecp returns non-sensitive status without secrets."""
    from backend.main import app
    tc = TestClient(app)

    with patch("backend.uecp.client.UECPClient.check_health", return_value={"configured": True, "reachable": True}):
        response = tc.get("/api/health/uecp")
        assert response.status_code == 200
        data = response.json()
        assert "configured" in data
        assert "reachable" in data
        # Ensure no secrets leak
        for sensitive_word in ("secret", "password", "key", "token"):
            assert sensitive_word not in response.text.lower()
