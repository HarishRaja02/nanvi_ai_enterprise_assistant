"""Acceptance tests for Phase 0: Central App Mode & Production Fail-Fast Hardening.

Proves:
1. APP_MODE defaults to 'production' if unset (fail-closed).
2. settings.is_production and settings.allows_synthetic_data API contract.
3. Production fail-fast startup validation rejects missing config or active demo flags.
4. Each forbidden path in production raises or returns DEPENDENCY_UNAVAILABLE:
   - SQLite fallback forbidden.
   - Mock LLM deterministic answerer forbidden.
   - Synthetic Gmail fallback forbidden.
   - Dev token routes forbidden.
   - Arbitrary folder browsing / updating forbidden.
5. Health and runtime settings endpoints accurately expose mode without secrets.
"""

from __future__ import annotations

import dataclasses
import os
import pytest
from fastapi.testclient import TestClient

from backend.core.config import Settings
from backend.core.exceptions import ConfigurationError, DependencyUnavailableError
from backend.main import app
from backend.security.models import UserIdentity
from backend.security.dependencies import get_current_user


def patch_settings(monkeypatch: pytest.MonkeyPatch, **kwargs) -> Settings:
    """Helper to update frozen settings across all module references."""
    import backend.core.config as config_mod
    import backend.api.routes as routes_mod
    import backend.api.settings_routes as settings_routes_mod
    import backend.api.dev_routes as dev_routes_mod
    import backend.bootstrap as bootstrap_mod
    import backend.main as main_mod

    new_settings = dataclasses.replace(config_mod.settings, **kwargs)
    monkeypatch.setattr(config_mod, "settings", new_settings)
    for mod in (routes_mod, settings_routes_mod, dev_routes_mod, bootstrap_mod, main_mod):
        if hasattr(mod, "settings"):
            monkeypatch.setattr(mod, "settings", new_settings)
    return new_settings


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("APP_MODE", raising=False)
    monkeypatch.delenv("APP_ENV", raising=False)


# ── 1. Fail-Closed Default & Mode Resolution ───────────────────────────────

def test_app_mode_defaults_to_production_when_unset(clean_env, monkeypatch: pytest.MonkeyPatch) -> None:
    """When neither APP_MODE nor APP_ENV is set, fail-closed default must be 'production'."""
    settings = Settings.from_env()
    assert settings.app_mode == "production"
    assert settings.is_production is True
    assert settings.allows_synthetic_data is False


def test_app_mode_explicit_modes(monkeypatch: pytest.MonkeyPatch) -> None:
    """Explicitly configured APP_MODE must be respected."""
    monkeypatch.setenv("APP_MODE", "development")
    dev_settings = Settings.from_env()
    assert dev_settings.app_mode == "development"
    assert dev_settings.is_development is True
    assert dev_settings.allows_synthetic_data is True

    monkeypatch.setenv("APP_MODE", "demo")
    demo_settings = Settings.from_env()
    assert demo_settings.app_mode == "demo"
    assert demo_settings.is_demo is True
    assert demo_settings.allows_synthetic_data is True

    monkeypatch.setenv("APP_MODE", "production")
    prod_settings = Settings.from_env()
    assert prod_settings.app_mode == "production"
    assert prod_settings.is_production is True
    assert prod_settings.allows_synthetic_data is False


def test_invalid_app_mode_fails_fast(monkeypatch: pytest.MonkeyPatch) -> None:
    """Any invalid or unrecognized APP_MODE must immediately raise ValueError."""
    monkeypatch.setenv("APP_MODE", "staging_invalid")
    with pytest.raises(ValueError, match="Invalid APP_MODE"):
        Settings.from_env()


# ── 2. Production Fail-Fast Startup Validation ──────────────────────────────

def test_production_fail_fast_missing_database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    """In production mode, validate_production_configuration must fail if DB URL is missing."""
    monkeypatch.setenv("APP_MODE", "production")
    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.setenv("SUPABASE_DATABASE_URL", "")
    monkeypatch.setenv("JWT_SECRET", "super-secret-key-at-least-32-chars-long")
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test")
    monkeypatch.setenv("COMPANY_FILE_ROOTS", "Customers=C:\\Data\\Customers;Finance=C:\\Data\\Finance;HR=C:\\Data\\HR;Projects=C:\\Data\\Projects;Contracts=C:\\Data\\Contracts")
    settings = Settings.from_env()
    with pytest.raises(ConfigurationError, match="DATABASE_URL or SUPABASE_DATABASE_URL"):
        settings.validate_production_configuration()


def test_production_fail_fast_missing_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    """In production mode, validate_production_configuration must fail if JWT/OIDC secrets are missing."""
    monkeypatch.setenv("APP_MODE", "production")
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/nanvi")
    monkeypatch.setenv("JWT_SECRET", "")
    monkeypatch.setenv("OIDC_ISSUER_URL", "")
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test")
    monkeypatch.setenv("COMPANY_FILE_ROOTS", "Customers=C:\\Data\\Customers;Finance=C:\\Data\\Finance;HR=C:\\Data\\HR;Projects=C:\\Data\\Projects;Contracts=C:\\Data\\Contracts")
    settings = Settings.from_env()
    with pytest.raises(ConfigurationError, match="JWT_SECRET or complete OIDC"):
        settings.validate_production_configuration()


def test_production_fail_fast_missing_llm_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """In production mode, validate_production_configuration must fail if Groq API key is missing."""
    monkeypatch.setenv("APP_MODE", "production")
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/nanvi")
    monkeypatch.setenv("JWT_SECRET", "super-secret-key-at-least-32-chars-long")
    monkeypatch.setenv("LLM_PROVIDER", "groq")
    monkeypatch.setenv("GROQ_API_KEY", "")
    monkeypatch.setenv("COMPANY_FILE_ROOTS", "Customers=C:\\Data\\Customers;Finance=C:\\Data\\Finance;HR=C:\\Data\\HR;Projects=C:\\Data\\Projects;Contracts=C:\\Data\\Contracts")
    settings = Settings.from_env()
    with pytest.raises(ConfigurationError, match="GROQ_API_KEY must be configured"):
        settings.validate_production_configuration()


def test_production_fail_fast_demo_auth_flag_forbidden(monkeypatch: pytest.MonkeyPatch) -> None:
    """In production mode, demo_auth_enabled=True must cause startup failure."""
    monkeypatch.setenv("APP_MODE", "production")
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/nanvi")
    monkeypatch.setenv("JWT_SECRET", "super-secret-key-at-least-32-chars-long")
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test")
    monkeypatch.setenv("DEMO_AUTH_ENABLED", "true")
    monkeypatch.setenv("COMPANY_FILE_ROOTS", "Customers=C:\\Data\\Customers;Finance=C:\\Data\\Finance;HR=C:\\Data\\HR;Projects=C:\\Data\\Projects;Contracts=C:\\Data\\Contracts")
    settings = Settings.from_env()
    with pytest.raises(ConfigurationError, match="DEMO_AUTH_ENABLED must be False"):
        settings.validate_production_configuration()


# ── 3. Forbidden Paths Raise / Return DEPENDENCY_UNAVAILABLE ────────────────

def test_production_forbids_sqlite_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    """In production mode, bootstrap must raise DependencyUnavailableError rather than falling back to SQLite."""
    patch_settings(
        monkeypatch,
        app_mode="production",
        database_url="postgresql://user:pass@localhost:5432/nanvi",
        supabase_database_url="",
    )

    from backend.integrations.database.postgres import PostgreSQLRepository

    def failing_init(self, *args, **kwargs):
        raise RuntimeError("Simulated production PostgreSQL outage")

    monkeypatch.setattr(PostgreSQLRepository, "__init__", failing_init)

    from backend.bootstrap import _create_agents, _create_authorization, _create_audit, _create_source_references, _create_tool_gateway, _create_retrieval_service

    auth = _create_authorization()
    audit = _create_audit()
    sources = _create_source_references(auth, audit)
    gateway = _create_tool_gateway(auth, audit)
    retrieval = _create_retrieval_service(auth, audit, sources)

    with pytest.raises(DependencyUnavailableError) as exc_info:
        _create_agents(retrieval, sources, gateway, auth, audit)

    assert exc_info.value.code == "DEPENDENCY_UNAVAILABLE"
    assert exc_info.value.dependency == "database"
    assert "SQLite fallback is forbidden in production" in str(exc_info.value)


def test_production_forbids_mock_llm_answerer(monkeypatch: pytest.MonkeyPatch) -> None:
    """In production mode, bootstrap must raise DependencyUnavailableError rather than using DeterministicTestAnswerer."""
    patch_settings(
        monkeypatch,
        app_mode="production",
        groq_api_key="",
        llm_provider="groq",
    )

    from backend.bootstrap import create_chat_service

    with pytest.raises(DependencyUnavailableError) as exc_info:
        create_chat_service()

    assert exc_info.value.code == "DEPENDENCY_UNAVAILABLE"
    assert exc_info.value.dependency == "llm"
    assert "mock deterministic answerer is forbidden in production" in str(exc_info.value)


def test_production_forbids_synthetic_gmail(monkeypatch: pytest.MonkeyPatch) -> None:
    """In production mode, Gmail provider must raise DependencyUnavailableError rather than returning sample emails."""
    patch_settings(monkeypatch, app_mode="production")

    from backend.integrations.email.gmail import GmailEmailProvider
    from backend.integrations.email.models import EmailProviderContext, EmailSearchRequest

    provider = GmailEmailProvider()
    ctx = EmailProviderContext(user_id="user1", tenant_id="tenant1", access_token="")
    req = EmailSearchRequest(query="financial")

    with pytest.raises(DependencyUnavailableError) as exc_info:
        provider.search_page(ctx, req)

    assert exc_info.value.code == "DEPENDENCY_UNAVAILABLE"
    assert exc_info.value.dependency == "email"


def test_production_forbids_dev_token_generation(monkeypatch: pytest.MonkeyPatch) -> None:
    """In production mode, dev token endpoint must reject with DEPENDENCY_UNAVAILABLE."""
    patch_settings(monkeypatch, app_mode="production")

    from backend.api.dev_routes import create_dev_token, DevTokenRequest
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        create_dev_token(DevTokenRequest())

    assert exc_info.value.status_code == 403
    assert "DEPENDENCY_UNAVAILABLE" in exc_info.value.detail


def test_production_forbids_arbitrary_folder_browse(monkeypatch: pytest.MonkeyPatch) -> None:
    """In production mode, POST /settings/company-folder/browse must return 403 DEPENDENCY_UNAVAILABLE."""
    patch_settings(monkeypatch, app_mode="production")

    client = TestClient(app)
    mock_user = UserIdentity(
        subject="test-user",
        issuer="test",
        tenant_id="tenant1",
        roles=["IT Admin"],
    )
    app.dependency_overrides[get_current_user] = lambda: mock_user

    try:
        response = client.post("/api/settings/company-folder/browse", json={"path": "C:\\Windows"})
        assert response.status_code == 403
        assert "DEPENDENCY_UNAVAILABLE" in response.json()["detail"]
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_production_forbids_arbitrary_folder_update_outside_roots(monkeypatch: pytest.MonkeyPatch) -> None:
    """In production mode, PUT /settings/company-folder outside allowed roots must return 403 DEPENDENCY_UNAVAILABLE."""
    patch_settings(
        monkeypatch,
        app_mode="production",
        company_file_roots=(("Finance", r"C:\AllowedCompanyData\Finance"),),
    )

    client = TestClient(app)
    mock_user = UserIdentity(
        subject="admin-user",
        issuer="test",
        tenant_id="tenant1",
        roles=["IT Admin"],
    )
    app.dependency_overrides[get_current_user] = lambda: mock_user

    try:
        response = client.put("/api/settings/company-folder", json={"path": r"C:\UnauthorizedFolder"})
        assert response.status_code == 403
        assert "DEPENDENCY_UNAVAILABLE" in response.json()["detail"]
    finally:
        app.dependency_overrides.pop(get_current_user, None)


# ── 4. Health and Settings Metadata Endpoints ───────────────────────────────

def test_health_endpoint_exposes_app_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    """GET /api/health must accurately expose app_mode and synthetic data policy."""
    patch_settings(monkeypatch, app_mode="demo")

    client = TestClient(app)
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["app_mode"] == "demo"
    assert data["is_production"] is False
    assert data["allows_synthetic_data"] is True


def test_settings_runtime_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    """GET /api/settings/runtime returns public capabilities without exposing secret values."""
    patch_settings(monkeypatch, app_mode="development")

    client = TestClient(app)
    response = client.get("/api/settings/runtime")
    assert response.status_code == 200
    data = response.json()
    assert data["app_mode"] == "development"
    assert data["is_production"] is False
    assert data["allows_synthetic_data"] is True
    assert data["demo_banner"] is True
    assert "features" in data
    # Ensure no secrets leak
    text = response.text
    assert "jwt_secret" not in text
    assert "groq_api_key" not in text
    assert "encryption_key" not in text


def test_production_readiness_fails_when_unhealthy(monkeypatch: pytest.MonkeyPatch) -> None:
    """GET /api/health/ready in production fails with 503 if required production config is missing."""
    patch_settings(
        monkeypatch,
        app_mode="production",
        database_url="",
        supabase_database_url="",
    )

    client = TestClient(app)
    response = client.get("/api/health/ready")
    assert response.status_code == 503
    assert "DEPENDENCY_UNAVAILABLE" in response.json()["detail"]
