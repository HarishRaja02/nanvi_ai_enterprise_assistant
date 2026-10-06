"""Explicit internal exception types for UECP integration."""
from __future__ import annotations


class UECPError(Exception):
    """Base exception for all UECP integration errors."""

    def __init__(self, message: str = "UECP platform error") -> None:
        super().__init__(message)
        self.message = message


class UECPUnavailable(UECPError):
    """Raised when UECP control plane is unreachable, times out, or returns a 5xx error."""

    def __init__(self, message: str = "UECP service is unavailable") -> None:
        super().__init__(message)


class UECPUnauthorized(UECPError):
    """Raised when Nanvi's application credentials or secrets are rejected by UECP (401)."""

    def __init__(self, message: str = "Invalid UECP application credentials") -> None:
        super().__init__(message)


class UECPAccessDenied(UECPError):
    """Base exception when access is denied by UECP."""

    def __init__(self, reason: str = "access_denied", message: str = "Access denied by UECP control plane") -> None:
        super().__init__(message)
        self.reason = reason


class UECPCredentialExpired(UECPAccessDenied):
    """Raised when the UECP credential has expired."""

    def __init__(self, message: str = "UECP credential has expired") -> None:
        super().__init__(reason="credential_expired", message=message)


class UECPCredentialFrozen(UECPAccessDenied):
    """Raised when the UECP credential is frozen."""

    def __init__(self, message: str = "UECP credential is frozen") -> None:
        super().__init__(reason="credential_frozen", message=message)


class UECPCredentialRevoked(UECPAccessDenied):
    """Raised when the UECP credential has been revoked."""

    def __init__(self, message: str = "UECP credential has been revoked") -> None:
        super().__init__(reason="credential_revoked", message=message)


class UECPParentFrozen(UECPAccessDenied):
    """Raised when a parent credential in the hierarchy is frozen."""

    def __init__(self, message: str = "Parent UECP credential is frozen") -> None:
        super().__init__(reason="parent_frozen", message=message)


class UECPInvalidResponse(UECPError):
    """Raised when UECP returns a malformed or non-compliant response."""

    def __init__(self, message: str = "Invalid or malformed response from UECP") -> None:
        super().__init__(message)


class UECPPermissionDenied(UECPAccessDenied):
    """Raised when an operation requires an entitlement that UECP did not grant."""

    def __init__(self, permission: str, message: str | None = None) -> None:
        msg = message or f"Missing required UECP entitlement: {permission}"
        super().__init__(reason=f"missing_entitlement:{permission}", message=msg)
        self.permission = permission
