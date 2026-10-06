"""Centralized UECP Authorization Service."""
from __future__ import annotations

import logging
from dataclasses import replace
from typing import Any

from backend.observability.logging import log_event
from backend.uecp.cache import UECPValidationCache
from backend.uecp.client import UECPClient
from backend.uecp.config import UECPConfig, get_uecp_config
from backend.uecp.exceptions import (
    UECPAccessDenied,
    UECPCredentialExpired,
    UECPCredentialFrozen,
    UECPCredentialRevoked,
    UECPInvalidResponse,
    UECPParentFrozen,
    UECPPermissionDenied,
    UECPUnauthorized,
    UECPUnavailable,
)
from backend.uecp.models import SafeUECPState, UECPAccessState

logger = logging.getLogger(__name__)


class UECPAuthorizationService:
    """Centralized service managing UECP credential validation, entitlement checks,

    fail-closed security policies, caching, and secure audit logging.
    """

    def __init__(
        self,
        config: UECPConfig | None = None,
        client: UECPClient | None = None,
        cache: UECPValidationCache | None = None,
        is_production: bool = False,
    ) -> None:
        self._config = config or get_uecp_config()
        self._cache = cache or UECPValidationCache(self._config.cache_ttl_seconds)
        self._client = client or UECPClient(self._config)
        self._is_production = is_production

    @property
    def cache(self) -> UECPValidationCache:
        return self._cache

    @property
    def client(self) -> UECPClient:
        return self._client

    def check_access(
        self,
        organization_id: str | None = None,
        permission: str | None = None,
        user_id: str | None = None,
        correlation_id: str | None = None,
    ) -> UECPAccessState:
        """Evaluate access authorization for an organization and optional permission.

        Enforces:
        - Cache retrieval with short TTL
        - Remote authoritative UECP control plane validation
        - Entitlement verification
        - Fail-closed behavior on outage or error
        - Strict security logging without secrets
        """
        # Controlled development bypass check
        if not self._config.enabled:
            if not self._is_production:
                # In development/test mode only, when explicitly disabled:
                return UECPAccessState(
                    allowed=True,
                    reason=None,
                    entitlements=tuple(["*"]),
                    organization_id=organization_id,
                    application_id=self._config.application_id or "nanvi-dev",
                )
            # In production, disabled UECP must FAIL CLOSED
            log_event(
                logger,
                "uecp_production_disabled_fail_closed",
                logging.CRITICAL,
                organization_id=organization_id,
                user_id=user_id,
                correlation_id=correlation_id,
            )
            return UECPAccessState(
                allowed=False,
                reason="uecp_disabled_in_production",
                organization_id=organization_id,
            )

        # 1. Check server-side short cache
        cached_decision = self._cache.get(organization_id, permission)
        if cached_decision is not None:
            return cached_decision

        # 2. Query UECP Control Plane
        try:
            state = self._client.validate_credential(
                organization_id=organization_id,
                permission=permission,
                correlation_id=correlation_id,
            )
        except (UECPUnavailable, UECPUnauthorized, UECPInvalidResponse) as exc:
            # FAIL CLOSED: Do not grant access on timeout, connection error, or invalid payload
            log_event(
                logger,
                "uecp_validation_failed_closed",
                logging.ERROR,
                organization_id=organization_id,
                user_id=user_id,
                correlation_id=correlation_id,
                reason=type(exc).__name__,
            )
            denied_state = UECPAccessState(
                allowed=False,
                reason="service_unavailable",
                organization_id=organization_id,
                application_id=self._config.application_id,
                status="unavailable",
            )
            # Short negative cache to protect against retry storms
            self._cache.set(organization_id, permission, denied_state, ttl_seconds=5)
            return denied_state
        except Exception as exc:
            log_event(
                logger,
                "uecp_validation_unexpected_error",
                logging.ERROR,
                organization_id=organization_id,
                user_id=user_id,
                correlation_id=correlation_id,
                error_type=type(exc).__name__,
            )
            denied_state = UECPAccessState(
                allowed=False,
                reason="service_unavailable",
                organization_id=organization_id,
                application_id=self._config.application_id,
                status="error",
            )
            self._cache.set(organization_id, permission, denied_state, ttl_seconds=5)
            return denied_state

        # 3. Check specific entitlements if requested and decision was positive
        if state.allowed and permission:
            if not state.can(permission):
                state = replace(
                    state,
                    allowed=False,
                    reason=f"missing_entitlement:{permission}",
                )

        # 4. Cache authoritative decision
        self._cache.set(organization_id, permission, state, ttl_seconds=self._config.cache_ttl_seconds)

        # 5. Security audit logging
        if state.allowed:
            log_event(
                logger,
                "uecp_validation_success",
                logging.INFO,
                organization_id=organization_id,
                user_id=user_id,
                correlation_id=correlation_id,
                permission=permission,
            )
        else:
            log_event(
                logger,
                "uecp_validation_denied",
                logging.WARNING,
                organization_id=organization_id,
                user_id=user_id,
                correlation_id=correlation_id,
                permission=permission,
                reason=state.reason,
            )

        return state

    def can(self, permission: str, organization_id: str | None = None) -> bool:
        """Convenience method to check if an entitlement is permitted."""
        state = self.check_access(organization_id=organization_id, permission=permission)
        return state.allowed

    def get_safe_state(self, organization_id: str | None = None) -> SafeUECPState:
        """Get safe non-sensitive state for frontend consumption."""
        if not self._config.enabled and not self._is_production:
            return SafeUECPState(connected=True, allowed=True, features={"*": True})

        state = self.check_access(organization_id=organization_id)
        return state.to_safe_frontend()


_service_instance: UECPAuthorizationService | None = None


def get_uecp_service() -> UECPAuthorizationService:
    global _service_instance
    if _service_instance is None:
        from backend.core.config import settings
        config = get_uecp_config()
        _service_instance = UECPAuthorizationService(
            config=config,
            is_production=settings.is_production,
        )
    return _service_instance


def set_uecp_service(service: UECPAuthorizationService | None) -> None:
    global _service_instance
    _service_instance = service
