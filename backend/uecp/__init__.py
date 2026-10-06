"""Universal Enterprise Control Plane (UECP) Integration Module for Nanvi AI Enterprise Assistant.

Centralized integration layer responsible for:
- Application identity & credential validation
- UECP platform authorization & access grants
- Entitlements & feature checks
- Fail-closed security & validation caching
"""
from __future__ import annotations

from backend.uecp.config import UECPConfig, get_uecp_config
from backend.uecp.exceptions import (
    UECPAccessDenied,
    UECPCredentialExpired,
    UECPCredentialFrozen,
    UECPCredentialRevoked,
    UECPError,
    UECPInvalidResponse,
    UECPParentFrozen,
    UECPPermissionDenied,
    UECPUnauthorized,
    UECPUnavailable,
)
from backend.uecp.models import SafeUECPState, UECPAccessState
from backend.uecp.client import UECPClient
from backend.uecp.cache import UECPValidationCache
from backend.uecp.authorization import UECPAuthorizationService, get_uecp_service
from backend.uecp.middleware import require_uecp_access

__all__ = [
    "UECPConfig",
    "get_uecp_config",
    "UECPError",
    "UECPUnavailable",
    "UECPUnauthorized",
    "UECPAccessDenied",
    "UECPCredentialExpired",
    "UECPCredentialFrozen",
    "UECPCredentialRevoked",
    "UECPParentFrozen",
    "UECPInvalidResponse",
    "UECPPermissionDenied",
    "UECPAccessState",
    "SafeUECPState",
    "UECPClient",
    "UECPValidationCache",
    "UECPAuthorizationService",
    "get_uecp_service",
    "require_uecp_access",
]
