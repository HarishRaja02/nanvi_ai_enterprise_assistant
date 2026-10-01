import pytest

from backend.security.audit import AuditLogger, InMemoryAuditSink
from backend.security.rate_limiting import NoOpRateLimiter, RateLimitExceeded, RateLimiter
from backend.security.secrets import EnvironmentSecretProvider, SecretNotFoundError, SecretsService
from backend.security.validation import InputValidationError, validate_non_empty
from fastapi import FastAPI
from fastapi.testclient import TestClient
from backend.security.headers import SecurityHeadersMiddleware


def test_environment_secret_provider_reads_configured_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEST_SECRET", "server-only-value")
    provider = EnvironmentSecretProvider()
    assert SecretsService(provider).get("TEST_SECRET") == "server-only-value"


def test_missing_secret_is_explicitly_rejected() -> None:
    provider = EnvironmentSecretProvider()
    with pytest.raises(SecretNotFoundError):
        provider.get_secret("DEFINITELY_NOT_CONFIGURED")


def test_secret_is_not_exposed_by_a_default_provider_object() -> None:
    provider = EnvironmentSecretProvider()
    assert not hasattr(provider, "secrets")


def test_audit_event_is_structured() -> None:
    sink = InMemoryAuditSink()
    logger = AuditLogger(sink)

    logger.record(
        event_type="authorization",
        outcome="deny",
        actor_id="user-1",
        tenant_id="tenant-1",
        resource_id="resource-1",
    )

    assert len(sink.events) == 1
    assert sink.events[0].outcome == "deny"
    assert sink.events[0].tenant_id == "tenant-1"


def test_noop_rate_limiter_is_explicit_development_behavior() -> None:
    NoOpRateLimiter().check("user-1")


def test_rate_limiter_contract_can_deny() -> None:
    class DenyAll(RateLimiter):
        def check(self, key: str) -> None:
            raise RateLimitExceeded(key)

    with pytest.raises(RateLimitExceeded):
        DenyAll().check("user-1")


def test_input_validation_rejects_empty_and_control_characters() -> None:
    with pytest.raises(InputValidationError):
        validate_non_empty("   ", "query")

    with pytest.raises(InputValidationError):
        validate_non_empty("hello\x00world", "query")


def test_input_validation_normalizes_whitespace() -> None:
    assert validate_non_empty("  hello  ", "query") == "hello"


def test_security_headers_are_added():
    app = FastAPI()
    app.add_middleware(SecurityHeadersMiddleware)

    @app.get("/")
    def root() -> dict[str, str]:
        return {"status": "ok"}

    response = TestClient(app).get("/")

    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "no-referrer"
