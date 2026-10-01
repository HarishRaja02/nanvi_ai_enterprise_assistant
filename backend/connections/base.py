"""Base provider contract, metadata, capabilities, and typed errors.

Every connection provider implements BaseProvider and declares its capabilities
via ProviderMetadata.  OAuth-only methods are never forced on non-OAuth providers.
"""
from __future__ import annotations

import enum
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Protocol


# ═══════════════════════════════════════════════════════════════
# Capabilities
# ═══════════════════════════════════════════════════════════════

class Capability(str, enum.Enum):
    """Capabilities a provider may declare."""
    OAUTH = "oauth"
    CREDENTIALS_FORM = "credentials_form"
    TEST = "test"
    REFRESH = "refresh"
    REVOKE = "revoke"
    READ_DOCUMENTS = "read_documents"
    QUERY_SQL = "query_sql"
    CALL_API = "call_api"
    SEND_EMAIL = "send_email"
    READ_EMAIL = "read_email"
    READ_REPOS = "read_repos"
    LIST_FILES = "list_files"
    WRITE_FILES = "write_files"


class AuthType(str, enum.Enum):
    """Authentication method the provider uses."""
    OAUTH2 = "oauth2"
    API_KEY = "api_key"
    DB_PASSWORD = "db_password"
    BASIC = "basic"
    BEARER = "bearer"
    SERVICE_ACCOUNT = "service_account"
    FILESYSTEM = "filesystem"
    NONE = "none"


class ConnectionStatus(str, enum.Enum):
    """Status of a stored connection."""
    CONNECTED = "CONNECTED"
    DISCONNECTED = "DISCONNECTED"
    ERROR = "ERROR"
    EXPIRED = "EXPIRED"
    REAUTH_REQUIRED = "REAUTH_REQUIRED"
    TESTING = "TESTING"


class ScopeLevel(str, enum.Enum):
    """Whether the connection belongs to a user or the organisation."""
    USER = "user"
    ORGANIZATION = "organization"


# ═══════════════════════════════════════════════════════════════
# Typed errors
# ═══════════════════════════════════════════════════════════════

class ConnectionError(Exception):
    """Base for all connection-layer errors."""
    friendly_message: str = "An unexpected connection error occurred."

    def __init__(self, message: str | None = None, *args: Any) -> None:
        if message:
            self.friendly_message = message
            super().__init__(message, *args)
        else:
            super().__init__(self.friendly_message, *args)


class InvalidCredentials(ConnectionError):
    friendly_message = "The credentials are invalid or have been revoked."


class Unreachable(ConnectionError):
    friendly_message = "The service could not be reached. Check the host and port."


class ConnectionTimeout(ConnectionError):
    friendly_message = "The connection timed out. The service may be slow or unreachable."


class TlsError(ConnectionError):
    friendly_message = "TLS/SSL verification failed. Check your SSL configuration."


class PermissionDenied(ConnectionError):
    friendly_message = "Access was denied. Check your credentials and permissions."


class InsufficientScope(ConnectionError):
    friendly_message = "The granted permissions are not sufficient for this operation."


class RateLimited(ConnectionError):
    friendly_message = "The service rate-limited the request. Please try again shortly."


class ProviderUnavailable(ConnectionError):
    friendly_message = "This provider is not currently available."


class OAuthDenied(ConnectionError):
    friendly_message = "Authorization was denied. You may have declined the consent prompt."


class OAuthExpired(ConnectionError):
    friendly_message = "Your authorization has expired. Please reconnect."


class AmbiguousConnection(ConnectionError):
    friendly_message = "Multiple connections match. Please specify which one to use."


class ReauthRequired(ConnectionError):
    friendly_message = "Re-authorization is required. Please reconnect."


class SSRFBlocked(ConnectionError):
    friendly_message = "The target address is not allowed for security reasons."


# ═══════════════════════════════════════════════════════════════
# Provider metadata
# ═══════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class ProviderMetadata:
    """Declarative metadata that drives the catalog UI and form rendering."""
    id: str
    name: str
    categories: tuple[str, ...]
    icon: str                          # icon name for the frontend
    description: str
    auth_type: AuthType
    capabilities: frozenset[Capability]
    available: bool = True
    available_reason: str = ""         # e.g. "not_configured" when env vars missing
    required_scopes: tuple[str, ...] = ()
    configuration_schema: dict[str, Any] = field(default_factory=dict)


# ═══════════════════════════════════════════════════════════════
# Base provider
# ═══════════════════════════════════════════════════════════════

class BaseProvider(ABC):
    """Contract that every connection provider must implement.

    Only the methods relevant to the provider's capabilities need real
    implementations.  The base class provides safe no-op defaults for
    optional methods.
    """

    @abstractmethod
    def get_metadata(self) -> ProviderMetadata:
        """Return static provider metadata (called once at registration)."""
        ...

    def get_capabilities(self) -> frozenset[Capability]:
        return self.get_metadata().capabilities

    # ── OAuth (optional) ─────────────────────────────────────────

    def get_authorization_url(self, *, user_id: str, tenant_id: str, redirect_uri: str,
                              state: str, pkce_verifier: str | None = None) -> str:
        raise ProviderUnavailable(f"{self.get_metadata().name} does not support OAuth")

    def handle_callback(self, *, code: str, state: str, redirect_uri: str,
                        pkce_verifier: str | None = None) -> dict[str, Any]:
        """Exchange an auth code for credentials.  Returns a dict with at least
        ``access_token``, and optionally ``refresh_token``, ``expires_in``,
        ``scope``, ``account_identifier``, ``display_name``, ``avatar_url``."""
        raise ProviderUnavailable(f"{self.get_metadata().name} does not support OAuth callback")

    # ── Credential form (optional) ───────────────────────────────

    def connect(self, config: dict[str, Any]) -> dict[str, Any]:
        """Validate and store form-based credentials.  Returns a dict with
        ``account_identifier``, ``display_name``, and the raw credentials to
        be encrypted before storage."""
        raise ProviderUnavailable(f"{self.get_metadata().name} does not support form connect")

    # ── Common lifecycle ─────────────────────────────────────────

    def test_connection(self, *, decrypted_credentials: dict[str, Any],
                        metadata_safe: dict[str, Any]) -> dict[str, Any]:
        """Test that the connection actually works.  Returns ``{"ok": True}``
        or raises a typed error."""
        raise ProviderUnavailable(f"{self.get_metadata().name} does not support testing")

    def refresh_credentials(self, *, decrypted_credentials: dict[str, Any]) -> dict[str, Any] | None:
        """Refresh tokens if possible.  Returns new credential dict or None if
        refresh is not applicable."""
        return None

    def disconnect(self, *, decrypted_credentials: dict[str, Any]) -> None:
        """Revoke at the provider if supported, then clean up."""
        pass

    def get_client(self, *, decrypted_credentials: dict[str, Any],
                   metadata_safe: dict[str, Any]) -> Any:
        """Return a scoped, ready-to-use client object for agent consumption.
        Agents never see raw credentials."""
        raise ProviderUnavailable(f"{self.get_metadata().name} does not provide a client")
