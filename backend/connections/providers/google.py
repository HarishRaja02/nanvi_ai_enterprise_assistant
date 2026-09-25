"""Google Workspace / Gmail Provider (OAuth 2.0)."""
from __future__ import annotations

import logging
import time
from typing import Any
from urllib.parse import urlencode

import httpx

from backend.connections.base import (
    AuthType,
    BaseProvider,
    Capability,
    ConnectionError,
    ConnectionTimeout,
    InvalidCredentials,
    OAuthDenied,
    OAuthExpired,
    ProviderMetadata,
    ProviderUnavailable,
    TlsError,
    Unreachable,
)
from backend.core.config import settings

logger = logging.getLogger(__name__)

GOOGLE_AUTH_BASE = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"
GOOGLE_REVOKE_URL = "https://oauth2.googleapis.com/revoke"

DEFAULT_GOOGLE_SCOPES = (
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
)


class GoogleProvider(BaseProvider):
    """Google Workspace / Gmail OAuth 2.0 provider."""

    def __init__(self, http_client: httpx.Client | None = None) -> None:
        self._client = http_client or httpx.Client(timeout=10.0)

    def get_metadata(self) -> ProviderMetadata:
        is_configured = bool(settings.google_client_id and settings.google_client_secret)
        return ProviderMetadata(
            id="google",
            name="Google Workspace",
            categories=("Communication", "Storage / Documents"),
            icon="google",
            description="Connect your Gmail and Google Drive accounts for automated workflows and search.",
            auth_type=AuthType.OAUTH2,
            capabilities=frozenset({
                Capability.OAUTH,
                Capability.TEST,
                Capability.REFRESH,
                Capability.REVOKE,
                Capability.READ_EMAIL,
                Capability.SEND_EMAIL,
                Capability.READ_DOCUMENTS,
            }),
            available=is_configured,
            available_reason="" if is_configured else "not_configured",
            required_scopes=DEFAULT_GOOGLE_SCOPES,
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
        if not settings.google_client_id:
            raise ProviderUnavailable("GOOGLE_CLIENT_ID is not configured on the server.")

        params = {
            "client_id": settings.google_client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": " ".join(DEFAULT_GOOGLE_SCOPES),
            "access_type": "offline",
            "prompt": "consent",
            "include_granted_scopes": "true",
            "state": state,
        }
        return f"{GOOGLE_AUTH_BASE}?{urlencode(params)}"

    def handle_callback(
        self,
        *,
        code: str,
        state: str,
        redirect_uri: str,
        pkce_verifier: str | None = None,
    ) -> dict[str, Any]:
        if not settings.google_client_id or not settings.google_client_secret:
            raise ProviderUnavailable("Google OAuth client is not configured.")

        payload = {
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
        }
        try:
            resp = self._client.post(GOOGLE_TOKEN_URL, data=payload)
        except Exception as exc:
            raise Unreachable(f"Could not reach Google OAuth servers: {exc}") from exc

        if resp.status_code != 200:
            logger.error("Google token exchange error: %s %s", resp.status_code, resp.text)
            raise OAuthDenied(f"Google authorization failed: {resp.text}")

        token_data = resp.json()
        access_token = token_data.get("access_token", "")
        refresh_token = token_data.get("refresh_token", "")
        expires_in = int(token_data.get("expires_in", 3600))
        granted_scope_str = token_data.get("scope", "")
        granted_scopes = [s for s in granted_scope_str.split(" ") if s]

        # Fetch profile info
        user_info = {}
        try:
            info_resp = self._client.get(
                GOOGLE_USERINFO_URL,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            if info_resp.status_code == 200:
                user_info = info_resp.json()
        except Exception as exc:
            logger.warning("Could not fetch Google profile: %s", exc)

        email = user_info.get("email") or "google-user"
        name = user_info.get("name") or email
        avatar_url = user_info.get("picture")

        expires_at = time.time() + expires_in

        return {
            "account_identifier": email,
            "display_name": f"Google Workspace ({email})",
            "credentials": {
                "access_token": access_token,
                "refresh_token": refresh_token,
                "token_expires_at": expires_at,
            },
            "metadata_safe": {
                "email": email,
                "name": name,
                "avatar_url": avatar_url,
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
            raise InvalidCredentials("No access token found.")

        try:
            resp = self._client.get(
                GOOGLE_USERINFO_URL,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            if resp.status_code == 200:
                data = resp.json()
                return {"ok": True, "email": data.get("email", ""), "verified": True}
            if resp.status_code in {401, 403}:
                # Try refresh if available
                ref_token = decrypted_credentials.get("refresh_token")
                if ref_token:
                    new_token, _ = self.refresh_access_token(ref_token)
                    resp2 = self._client.get(
                        GOOGLE_USERINFO_URL,
                        headers={"Authorization": f"Bearer {new_token}"},
                    )
                    if resp2.status_code == 200:
                        return {"ok": True, "email": resp2.json().get("email", ""), "refreshed": True}
                raise InvalidCredentials("Google authorization expired or was revoked.")
            raise ConnectionError(f"Google API returned HTTP {resp.status_code}")
        except InvalidCredentials:
            raise
        except Exception as exc:
            raise ConnectionError(f"Error testing Google connection: {exc}") from exc

    def refresh_credentials(
        self,
        *,
        decrypted_credentials: dict[str, Any],
    ) -> dict[str, Any] | None:
        refresh_token = decrypted_credentials.get("refresh_token")
        if not refresh_token:
            return None

        expires_at = decrypted_credentials.get("token_expires_at", 0)
        # Refresh if expires in less than 5 minutes
        if expires_at - time.time() > 300:
            return None

        try:
            new_access_token, expires_in = self.refresh_access_token(refresh_token)
            updated = dict(decrypted_credentials)
            updated["access_token"] = new_access_token
            updated["token_expires_at"] = time.time() + expires_in
            return updated
        except Exception as exc:
            logger.warning("Failed refreshing Google credentials: %s", exc)
            return None

    def refresh_access_token(self, refresh_token: str) -> tuple[str, int]:
        if not settings.google_client_id or not settings.google_client_secret:
            raise ProviderUnavailable("Google OAuth client missing.")

        payload = {
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        }
        resp = self._client.post(GOOGLE_TOKEN_URL, data=payload)
        if resp.status_code != 200:
            raise InvalidCredentials(f"Failed to refresh Google token: {resp.text}")

        data = resp.json()
        return data.get("access_token", ""), int(data.get("expires_in", 3600))

    def disconnect(self, *, decrypted_credentials: dict[str, Any]) -> None:
        token = decrypted_credentials.get("access_token") or decrypted_credentials.get("refresh_token")
        if token:
            try:
                self._client.post(GOOGLE_REVOKE_URL, params={"token": token})
            except Exception as exc:
                logger.warning("Error revoking Google token: %s", exc)

    def get_client(
        self,
        *,
        decrypted_credentials: dict[str, Any],
        metadata_safe: dict[str, Any],
    ) -> Any:
        from backend.integrations.email.gmail import GmailEmailProvider
        from backend.integrations.email.models import UserEmailAccount

        email = metadata_safe.get("email") or ""
        token = decrypted_credentials.get("access_token") or ""
        ref_token = decrypted_credentials.get("refresh_token") or ""

        account = UserEmailAccount(
            id=email,
            user_id="connection-user",
            email_address=email,
            display_name=metadata_safe.get("name", email),
            provider="google",
            access_token=token,
            refresh_token=ref_token,
            avatar_url=metadata_safe.get("avatar_url"),
        )
        return GmailEmailProvider(account=account)
