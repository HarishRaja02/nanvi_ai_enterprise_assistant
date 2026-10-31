"""Microsoft 365 / Outlook / OneDrive / SharePoint OAuth 2.0 & Graph Provider."""
from __future__ import annotations

import logging
import os
import time
from typing import Any
from urllib.parse import urlencode

import httpx

from backend.connections.base import (
    AuthType,
    BaseProvider,
    Capability,
    ConnectionError,
    InvalidCredentials,
    OAuthDenied,
    ProviderMetadata,
    ProviderUnavailable,
    Unreachable,
)
from backend.core.config import settings

logger = logging.getLogger(__name__)

MS_AUTH_BASE = "https://login.microsoftonline.com/common/oauth2/v2.0/authorize"
MS_TOKEN_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
MS_GRAPH_ME = "https://graph.microsoft.com/v1.0/me"

DEFAULT_MICROSOFT_SCOPES = (
    "openid",
    "profile",
    "email",
    "offline_access",
    "User.Read",
    "Mail.Read",
    "Mail.ReadWrite",
    "Mail.Send",
    "Files.Read",
    "Files.Read.All",
    "Sites.Read.All",
)


def _get_ms_client_id() -> str:
    return os.getenv("MICROSOFT_CLIENT_ID") or os.getenv("AZURE_CLIENT_ID") or ""


def _get_ms_client_secret() -> str:
    return os.getenv("MICROSOFT_CLIENT_SECRET") or os.getenv("AZURE_CLIENT_SECRET") or ""


class Microsoft365Provider(BaseProvider):
    """Microsoft 365 Suite provider (Outlook, OneDrive, SharePoint, Teams)."""

    def __init__(self, http_client: httpx.Client | None = None) -> None:
        self._client = http_client or httpx.Client(timeout=10.0)

    def get_metadata(self) -> ProviderMetadata:
        cid = _get_ms_client_id()
        csec = _get_ms_client_secret()
        is_configured = bool(cid and csec)
        return ProviderMetadata(
            id="microsoft365",
            name="Microsoft 365",
            categories=("Email", "Cloud Storage", "Office Documents", "Communication"),
            icon="microsoft365",
            description="Connect Microsoft 365 for Outlook email, OneDrive documents, and SharePoint sites.",
            auth_type=AuthType.OAUTH2,
            capabilities=frozenset({
                Capability.OAUTH,
                Capability.TEST,
                Capability.REFRESH,
                Capability.REVOKE,
                Capability.READ_EMAIL,
                Capability.SEND_EMAIL,
                Capability.READ_DOCUMENTS,
                Capability.LIST_FILES,
            }),
            available=is_configured,
            available_reason="" if is_configured else "not_configured",
            required_scopes=DEFAULT_MICROSOFT_SCOPES,
        )

    def get_authorization_url(
        self,
        *,
        user_id: str,
        tenant_id: str,
        redirect_uri: str,
        state: str,
        pkce_verifier: str | None = None,
    ) -> str:
        cid = _get_ms_client_id()
        if not cid:
            raise ProviderUnavailable("MICROSOFT_CLIENT_ID is not configured on the server.")

        params = {
            "client_id": cid,
            "response_type": "code",
            "redirect_uri": redirect_uri,
            "response_mode": "query",
            "scope": " ".join(DEFAULT_MICROSOFT_SCOPES),
            "state": state,
            "prompt": "consent",
        }
        return f"{MS_AUTH_BASE}?{urlencode(params)}"

    def handle_callback(
        self,
        *,
        code: str,
        state: str,
        redirect_uri: str,
        pkce_verifier: str | None = None,
    ) -> dict[str, Any]:
        cid = _get_ms_client_id()
        csec = _get_ms_client_secret()
        if not cid or not csec:
            raise ProviderUnavailable("Microsoft OAuth credentials not configured.")

        payload = {
            "client_id": cid,
            "client_secret": csec,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
            "scope": " ".join(DEFAULT_MICROSOFT_SCOPES),
        }
        try:
            resp = self._client.post(MS_TOKEN_URL, data=payload)
        except Exception as exc:
            raise Unreachable(f"Could not reach Microsoft OAuth endpoint: {exc}") from exc

        if resp.status_code != 200:
            raise OAuthDenied(f"Microsoft authorization failed: {resp.text}")

        data = resp.json()
        access_token = data.get("access_token", "")
        refresh_token = data.get("refresh_token", "")
        expires_in = int(data.get("expires_in", 3600))
        granted_scope_str = data.get("scope", "")
        granted_scopes = [s for s in granted_scope_str.split(" ") if s]

        # Fetch profile
        user_info = {}
        try:
            me_resp = self._client.get(
                MS_GRAPH_ME,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            if me_resp.status_code == 200:
                user_info = me_resp.json()
        except Exception as exc:
            logger.warning("Could not fetch Microsoft profile: %s", exc)

        email = user_info.get("mail") or user_info.get("userPrincipalName") or "m365-user"
        name = user_info.get("displayName") or email

        return {
            "account_identifier": email,
            "display_name": f"Microsoft 365 ({email})",
            "credentials": {
                "access_token": access_token,
                "refresh_token": refresh_token,
                "token_expires_at": time.time() + expires_in,
            },
            "metadata_safe": {
                "email": email,
                "name": name,
                "user_principal_name": user_info.get("userPrincipalName"),
                "job_title": user_info.get("jobTitle"),
            },
            "granted_scopes": granted_scopes,
        }

    def test_connection(
        self,
        *,
        decrypted_credentials: dict[str, Any],
        metadata_safe: dict[str, Any],
    ) -> dict[str, Any]:
        access_token = decrypted_credentials.get("access_token", "")
        if not access_token:
            raise InvalidCredentials("No Microsoft access token found.")

        try:
            resp = self._client.get(
                MS_GRAPH_ME,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            if resp.status_code == 200:
                data = resp.json()
                return {"ok": True, "email": data.get("mail") or data.get("userPrincipalName", ""), "verified": True}
            if resp.status_code in {401, 403}:
                raise InvalidCredentials("Microsoft authorization expired or was revoked.")
            raise ConnectionError(f"Microsoft Graph API returned HTTP {resp.status_code}")
        except InvalidCredentials:
            raise
        except Exception as exc:
            raise ConnectionError(f"Error testing Microsoft connection: {exc}") from exc


class OutlookProvider(Microsoft365Provider):
    """Standalone Outlook email provider."""

    def get_metadata(self) -> ProviderMetadata:
        cid = _get_ms_client_id()
        csec = _get_ms_client_secret()
        is_configured = bool(cid and csec)
        return ProviderMetadata(
            id="outlook",
            name="Microsoft Outlook",
            categories=("Email", "Communication"),
            icon="outlook",
            description="Connect Microsoft Outlook for reading, searching, and managing email threads.",
            auth_type=AuthType.OAUTH2,
            capabilities=frozenset({
                Capability.OAUTH,
                Capability.TEST,
                Capability.REFRESH,
                Capability.READ_EMAIL,
                Capability.SEND_EMAIL,
            }),
            available=is_configured,
            available_reason="" if is_configured else "not_configured",
            required_scopes=("Mail.Read", "Mail.ReadWrite", "Mail.Send"),
        )


class OneDriveProvider(Microsoft365Provider):
    """Standalone OneDrive cloud storage provider."""

    def get_metadata(self) -> ProviderMetadata:
        cid = _get_ms_client_id()
        csec = _get_ms_client_secret()
        is_configured = bool(cid and csec)
        return ProviderMetadata(
            id="onedrive",
            name="Microsoft OneDrive",
            categories=("Cloud Storage", "Office Documents"),
            icon="onedrive",
            description="Search and retrieve personal and corporate OneDrive cloud documents.",
            auth_type=AuthType.OAUTH2,
            capabilities=frozenset({
                Capability.OAUTH,
                Capability.TEST,
                Capability.REFRESH,
                Capability.READ_DOCUMENTS,
                Capability.LIST_FILES,
            }),
            available=is_configured,
            available_reason="" if is_configured else "not_configured",
            required_scopes=("Files.Read", "Files.Read.All"),
        )


class SharePointProvider(Microsoft365Provider):
    """Standalone SharePoint document libraries provider."""

    def get_metadata(self) -> ProviderMetadata:
        cid = _get_ms_client_id()
        csec = _get_ms_client_secret()
        is_configured = bool(cid and csec)
        return ProviderMetadata(
            id="sharepoint",
            name="Microsoft SharePoint",
            categories=("Cloud Storage", "Office Documents"),
            icon="sharepoint",
            description="Access corporate team sites, document libraries, and authorized folders.",
            auth_type=AuthType.OAUTH2,
            capabilities=frozenset({
                Capability.OAUTH,
                Capability.TEST,
                Capability.REFRESH,
                Capability.READ_DOCUMENTS,
                Capability.LIST_FILES,
            }),
            available=is_configured,
            available_reason="" if is_configured else "not_configured",
            required_scopes=("Sites.Read.All",),
        )
