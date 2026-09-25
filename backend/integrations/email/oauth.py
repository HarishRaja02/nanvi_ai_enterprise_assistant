"""Google OAuth 2.0 Authentication & Token Lifecycle Engine.

Handles authorization URL generation, code-for-token exchange, user profile fetching,
and automatic background token refreshes for per-user Google Workspace / Gmail access.
"""
from __future__ import annotations

import base64
import json
import logging
import time
import uuid
from typing import Any
from urllib.parse import urlencode

import httpx

from backend.core.config import settings

logger = logging.getLogger(__name__)

GOOGLE_AUTH_BASE = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"

GMAIL_SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
    "https://www.googleapis.com/auth/gmail.readonly",
]


class GoogleOAuthService:
    """Manages OAuth 2.0 interactions with Google Identity Platform."""

    def __init__(self, http_client: httpx.Client | None = None) -> None:
        self._client = http_client or httpx.Client(timeout=10.0)

    def generate_auth_url(
        self,
        user_id: str,
        tenant_id: str = "enterprise-tenant",
        redirect_uri: str = "http://localhost:5173/auth/google/callback",
    ) -> str:
        """Generate a Google OAuth 2.0 authorization URL with offline consent."""
        if not settings.google_client_id:
            raise ValueError("GOOGLE_CLIENT_ID is not configured in backend environment")

        state_data = {
            "uid": user_id,
            "tid": tenant_id,
            "ts": time.time(),
            "n": uuid.uuid4().hex[:12],
        }
        state_encoded = base64.urlsafe_b64encode(json.dumps(state_data).encode()).decode()

        params = {
            "client_id": settings.google_client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": " ".join(GMAIL_SCOPES),
            "access_type": "offline",
            "prompt": "consent",
            "include_granted_scopes": "true",
            "state": state_encoded,
        }
        return f"{GOOGLE_AUTH_BASE}?{urlencode(params)}"

    def decode_state(self, state: str) -> dict[str, Any]:
        """Decode and validate the OAuth state parameter."""
        try:
            raw = base64.urlsafe_b64decode(state.encode()).decode()
            return json.loads(raw)
        except Exception as exc:
            logger.warning("Invalid OAuth state received: %s", exc)
            return {}

    def exchange_code(
        self,
        code: str,
        redirect_uri: str = "http://localhost:5173/auth/google/callback",
    ) -> dict[str, Any]:
        """Exchange authorization code for access and refresh tokens."""
        if not settings.google_client_id or not settings.google_client_secret:
            raise ValueError("Google OAuth credentials (client_id / client_secret) are not configured")

        payload = {
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
        }
        response = self._client.post(GOOGLE_TOKEN_URL, data=payload)
        if response.status_code != 200:
            logger.error("Google token exchange failed: %s %s", response.status_code, response.text)
            raise RuntimeError(f"Google token exchange failed: {response.text}")

        return response.json()

    def fetch_userinfo(self, access_token: str) -> dict[str, Any]:
        """Retrieve Google user profile (email, name, picture) using access token."""
        headers = {"Authorization": f"Bearer {access_token}"}
        resp = self._client.get(GOOGLE_USERINFO_URL, headers=headers)
        if resp.status_code != 200:
            logger.warning("Could not fetch Google user info: %s %s", resp.status_code, resp.text)
            return {}
        return resp.json()

    def refresh_access_token(self, refresh_token: str) -> tuple[str, int]:
        """Obtain a fresh access token using a refresh token. Returns (access_token, expires_in)."""
        if not settings.google_client_id or not settings.google_client_secret:
            raise ValueError("Google OAuth credentials missing")

        payload = {
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        }
        resp = self._client.post(GOOGLE_TOKEN_URL, data=payload)
        if resp.status_code != 200:
            logger.error("Failed to refresh Google token: %s", resp.text)
            raise RuntimeError(f"Google token refresh failed: {resp.text}")

        data = resp.json()
        access_token = data.get("access_token", "")
        expires_in = data.get("expires_in", 3600)
        return access_token, expires_in


_oauth_service: GoogleOAuthService | None = None


def get_google_oauth_service() -> GoogleOAuthService:
    global _oauth_service
    if _oauth_service is None:
        _oauth_service = GoogleOAuthService()
    return _oauth_service
