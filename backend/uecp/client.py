"""Server-side reusable HTTP client for Universal Enterprise Control Plane (UECP)."""
from __future__ import annotations

import logging
from typing import Any
import uuid

import httpx

from backend.observability.logging import log_event, sanitize
from backend.uecp.config import UECPConfig, get_uecp_config
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
from backend.uecp.models import UECPAccessState

logger = logging.getLogger(__name__)


class UECPClient:
    """Client for UECP control plane validation endpoint."""

    def __init__(self, config: UECPConfig | None = None, http_client: httpx.Client | None = None) -> None:
        self._config = config or get_uecp_config()
        self._client = http_client

    def _get_http_client(self) -> httpx.Client:
        if self._client is not None:
            return self._client
        # Dedicated client with configured timeout
        return httpx.Client(
            timeout=self._config.validation_timeout_seconds,
            follow_redirects=False,
        )

    def validate_credential(
        self,
        organization_id: str | None = None,
        permission: str | None = None,
        correlation_id: str | None = None,
    ) -> UECPAccessState:
        """Call POST /api/v1/credentials/validate on UECP control plane.

        Fails closed on any error, returning or raising explicit typed outcomes.
        """
        config = self._config
        if not config.base_url:
            raise UECPUnavailable("UECP base URL is not configured")

        # Validate HTTPS security requirement
        if not config.allow_insecure_http and not config.base_url.startswith("https://"):
            raise UECPUnavailable("Insecure HTTP communication with UECP is prohibited")

        url = f"{config.base_url}/api/v1/credentials/validate"
        cid = correlation_id or str(uuid.uuid4())

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-Application-ID": config.application_id,
            "X-Application-Key": config.application_key,
            "X-Credential-ID": config.credential_id,
            "X-Request-ID": cid,
            "X-Correlation-ID": cid,
        }

        payload: dict[str, Any] = {
            "application_id": config.application_id,
            "application_key": config.application_key,
            "credential_id": config.credential_id,
            "credential_secret": config.credential_secret,
        }
        if organization_id:
            payload["organization_id"] = organization_id
        if permission:
            payload["permission"] = permission

        client = self._get_http_client()
        response: httpx.Response | None = None

        try:
            response = client.post(url, json=payload, headers=headers)
        except (httpx.TimeoutException, httpx.ConnectTimeout, httpx.ReadTimeout) as exc:
            log_event(
                logger,
                "uecp_call_timeout",
                logging.WARNING,
                organization_id=organization_id,
                correlation_id=cid,
                error="timeout",
            )
            raise UECPUnavailable("UECP validation timed out") from exc
        except (httpx.ConnectError, httpx.NetworkError, httpx.TransportError) as exc:
            log_event(
                logger,
                "uecp_connection_failed",
                logging.WARNING,
                organization_id=organization_id,
                correlation_id=cid,
                error="connection_failed",
            )
            raise UECPUnavailable("UECP service is unreachable") from exc
        except Exception as exc:
            log_event(
                logger,
                "uecp_call_exception",
                logging.ERROR,
                organization_id=organization_id,
                correlation_id=cid,
                error_type=type(exc).__name__,
            )
            raise UECPUnavailable("UECP validation encountered network error") from exc

        # Handle HTTP status codes
        if response.status_code == 401:
            log_event(
                logger,
                "uecp_unauthorized",
                logging.ERROR,
                organization_id=organization_id,
                correlation_id=cid,
            )
            raise UECPUnauthorized("UECP rejected application credentials")

        if response.status_code >= 500:
            log_event(
                logger,
                "uecp_server_error",
                logging.ERROR,
                status_code=response.status_code,
                organization_id=organization_id,
                correlation_id=cid,
            )
            raise UECPUnavailable(f"UECP server error ({response.status_code})")

        if response.status_code not in {200, 403}:
            log_event(
                logger,
                "uecp_unexpected_status",
                logging.WARNING,
                status_code=response.status_code,
                organization_id=organization_id,
                correlation_id=cid,
            )
            raise UECPInvalidResponse(f"Unexpected status from UECP: {response.status_code}")

        # Parse JSON response body
        try:
            data = response.json()
        except Exception as exc:
            log_event(
                logger,
                "uecp_malformed_response",
                logging.ERROR,
                organization_id=organization_id,
                correlation_id=cid,
            )
            raise UECPInvalidResponse("UECP response could not be parsed as JSON") from exc

        if not isinstance(data, dict):
            raise UECPInvalidResponse("UECP response must be a JSON object")

        # Extract authorization decision
        raw_allowed = data.get("allowed")
        if raw_allowed is None:
            # Check fallback fields like "valid" or status
            if "valid" in data:
                allowed = bool(data["valid"])
            else:
                allowed = response.status_code == 200
        else:
            allowed = bool(raw_allowed)

        reason = data.get("reason")
        status_val = str(data.get("status", "active" if allowed else "denied")).lower()

        # Extract entitlements list
        raw_entitlements = data.get("entitlements", [])
        if isinstance(raw_entitlements, list):
            entitlements = tuple(str(e) for e in raw_entitlements)
        elif isinstance(raw_entitlements, (set, tuple)):
            entitlements = tuple(str(e) for e in raw_entitlements)
        else:
            entitlements = tuple()

        # Classify reasons if access is denied
        if not allowed:
            r = str(reason).lower() if reason else status_val
            if "frozen" in r or status_val == "frozen":
                if "parent" in r:
                    reason = "parent_frozen"
                else:
                    reason = "credential_frozen"
            elif "expired" in r or status_val == "expired":
                reason = "credential_expired"
            elif "revoked" in r or status_val == "revoked":
                reason = "credential_revoked"
            elif not reason:
                reason = "access_denied"

        return UECPAccessState(
            allowed=allowed,
            reason=reason if not allowed else None,
            entitlements=entitlements,
            organization_id=organization_id,
            application_id=config.application_id,
            status=status_val,
        )

    def check_health(self) -> dict[str, bool]:
        """Check if UECP integration is configured and the control plane is reachable.

        Safe probe with no exposed credentials or secrets.
        """
        if not self._config.enabled or not self._config.base_url:
            return {"configured": False, "reachable": False}

        url = f"{self._config.base_url}/api/v1/health"
        client = self._get_http_client()
        try:
            resp = client.get(url, timeout=min(5.0, self._config.validation_timeout_seconds))
            reachable = resp.status_code in {200, 204}
        except Exception:
            reachable = False

        return {"configured": True, "reachable": reachable}
