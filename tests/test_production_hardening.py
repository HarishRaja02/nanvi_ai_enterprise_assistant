from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from backend.core.config import Settings
from backend.main import app
from backend.security.rate_limiting import InMemoryFixedWindowRateLimiter, RateLimitExceeded


def test_production_settings_require_explicit_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("DATABASE_URL", "postgresql://example")
    monkeypatch.setenv("REDIS_URL", "redis://example")
    monkeypatch.setenv("COMPANY_FILE_ROOTS", "Customers=C:\\CompanyData\\Customers;Finance=C:\\CompanyData\\Finance;HR=C:\\CompanyData\\HR;Projects=C:\\CompanyData\\Projects;Contracts=C:\\CompanyData\\Contracts")
    settings = Settings.from_env()
    assert settings.app_env == "production"
    assert settings.debug is False
    assert settings.hsts_enabled is True


def test_invalid_environment_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "prod")
    with pytest.raises(ValueError):
        Settings.from_env()


def test_rate_limiter_enforces_fixed_window() -> None:
    limiter = InMemoryFixedWindowRateLimiter(max_requests=2, window_seconds=60)
    limiter.check("u1")
    limiter.check("u1")
    with pytest.raises(RateLimitExceeded):
        limiter.check("u1")
    limiter.check("u2")


def test_health_headers_and_request_id() -> None:
    response = TestClient(app).get("/api/health/live")
    assert response.status_code == 200
    assert response.headers["x-request-id"]
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["content-security-policy"]


def test_health_endpoint_basic_latency() -> None:
    client = TestClient(app)
    durations = []
    for _ in range(20):
        start = time.perf_counter()
        response = client.get("/api/health/live")
        durations.append(time.perf_counter() - start)
        assert response.status_code == 200
    durations.sort()
    p95 = durations[int(len(durations) * 0.95) - 1]
    # Regression guard for the lightweight liveness endpoint, not a production SLA.
    assert p95 < 0.25


def test_production_file_roots_must_be_exactly_allowlisted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("COMPANY_FILE_ROOTS", "Customers=C:\\CompanyData\\Customers;Finance=C:\\CompanyData\\Finance")
    with pytest.raises(ValueError):
        Settings.from_env()
