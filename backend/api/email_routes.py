"""Email Integration API routes for multi-user mailbox authorization and Google OAuth 2.0.

Provides endpoints for initiating Google OAuth, exchanging authorization codes,
managing connected email accounts, checking mailbox status, and disconnecting accounts.
"""
from __future__ import annotations

import logging
import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from backend.integrations.email.oauth import get_google_oauth_service
from backend.integrations.email.user_account_service import (
    UserEmailAccount,
    get_user_email_account_service,
)
from backend.observability.logging import log_event
from backend.security.dependencies import get_current_user
from backend.security.models import UserIdentity

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/email", tags=["email"])


class OAuthCallbackRequest(BaseModel):
    code: str = Field(min_length=1)
    state: str | None = None
    redirect_uri: str | None = None


class ManualConnectRequest(BaseModel):
    email_address: str = Field(min_length=3, max_length=255)
    display_name: str | None = None
    refresh_token: str | None = None
    access_token: str | None = None


class DisconnectRequest(BaseModel):
    account_id: str | None = None


@router.get("/oauth/google/url")
def get_google_auth_url(
    redirect_uri: str | None = Query(default=None),
    user: UserIdentity = Depends(get_current_user),
) -> dict[str, str]:
    """Generate a Google OAuth 2.0 authorization URL for connecting a mailbox."""
    from backend.core.config import settings
    oauth = get_google_oauth_service()
    effective_uri = redirect_uri or settings.google_redirect_uri or "http://localhost:5173"
    try:
        url = oauth.generate_auth_url(
            user_id=user.subject,
            tenant_id=user.tenant_id or "enterprise-tenant",
            redirect_uri=effective_uri,
        )
        return {"auth_url": url, "redirect_uri": effective_uri}
    except Exception as exc:
        logger.error("Failed to generate Google auth URL: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate Google auth URL: {exc}",
        )


@router.post("/oauth/google/callback")
def handle_google_callback(
    body: OAuthCallbackRequest,
    user: UserIdentity = Depends(get_current_user),
) -> dict[str, Any]:
    """Exchange authorization code from Google OAuth and save the connected mailbox."""
    from backend.core.config import settings
    oauth = get_google_oauth_service()
    account_service = get_user_email_account_service()

    redirect_uri = body.redirect_uri or settings.google_redirect_uri or "http://localhost:5173"

    try:
        token_data = oauth.exchange_code(body.code, redirect_uri=redirect_uri)
    except Exception as exc:
        logger.error("Token exchange with Google failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Google authorization failed: {exc}",
        )

    access_token = token_data.get("access_token", "")
    refresh_token = token_data.get("refresh_token", "")
    expires_in = token_data.get("expires_in", 3600)
    scopes = token_data.get("scope", "gmail.readonly")

    # Fetch user's Google profile
    userinfo = oauth.fetch_userinfo(access_token) if access_token else {}
    email_address = userinfo.get("email") or f"{user.subject}@gmail.com"
    display_name = userinfo.get("name") or user.name or "Google Workspace User"
    avatar_url = userinfo.get("picture")

    # If Google did not return a new refresh token (e.g. user already consented previously),
    # preserve existing stored refresh token for this user
    if not refresh_token:
        existing = account_service.get_active_account(user.subject)
        if existing and existing.refresh_token:
            refresh_token = existing.refresh_token

    account = UserEmailAccount(
        id="",
        user_id=user.subject,
        tenant_id=user.tenant_id or "enterprise-tenant",
        email_address=email_address,
        display_name=display_name,
        provider="google",
        access_token=access_token,
        refresh_token=refresh_token,
        token_expires_at=time.time() + expires_in,
        scopes=scopes,
        avatar_url=avatar_url,
        is_active=True,
    )
    saved = account_service.save_account(account)

    log_event(
        logger,
        "email_account_connected",
        actor_id=user.subject,
        tenant_id=user.tenant_id,
        email_address=email_address,
        provider="google",
    )

    return {
        "status": "connected",
        "account": {
            "id": saved.id,
            "email_address": saved.email_address,
            "display_name": saved.display_name,
            "provider": saved.provider,
            "avatar_url": saved.avatar_url,
            "connected_at": saved.connected_at,
        },
    }


@router.get("/status")
def get_mailbox_status(user: UserIdentity = Depends(get_current_user)) -> dict[str, Any]:
    """Get the current user's connected mailbox status."""
    account_service = get_user_email_account_service()
    account = account_service.get_active_account(user.subject)

    if account:
        return {
            "connected": True,
            "account": {
                "id": account.id,
                "email_address": account.email_address,
                "display_name": account.display_name,
                "provider": account.provider,
                "avatar_url": account.avatar_url,
                "connected_at": account.connected_at,
                "last_synced_at": account.last_synced_at,
            },
        }

    # If no account connected yet, check if enterprise fallback token is configured in .env
    from backend.core.config import settings
    has_enterprise_fallback = bool(settings.gmail_refresh_token or settings.gmail_access_token)

    return {
        "connected": False,
        "account": None,
        "has_enterprise_fallback": has_enterprise_fallback,
    }


@router.get("/accounts")
def list_user_accounts(user: UserIdentity = Depends(get_current_user)) -> list[dict[str, Any]]:
    """List all connected email mailboxes for the current user."""
    account_service = get_user_email_account_service()
    accounts = account_service.get_accounts(user.subject)
    return [
        {
            "id": a.id,
            "email_address": a.email_address,
            "display_name": a.display_name,
            "provider": a.provider,
            "avatar_url": a.avatar_url,
            "connected_at": a.connected_at,
            "is_active": a.is_active,
        }
        for a in accounts
    ]


@router.post("/disconnect")
def disconnect_mailbox(
    body: DisconnectRequest | None = None,
    user: UserIdentity = Depends(get_current_user),
) -> dict[str, str]:
    """Disconnect the active or specified mailbox for the current user."""
    account_service = get_user_email_account_service()
    account_id = body.account_id if body else None
    account_service.disconnect_account(user.subject, account_id=account_id)

    log_event(
        logger,
        "email_account_disconnected",
        actor_id=user.subject,
        tenant_id=user.tenant_id,
        account_id=account_id,
    )
    return {"status": "disconnected"}


@router.post("/manual-connect")
def manual_connect_mailbox(
    body: ManualConnectRequest,
    user: UserIdentity = Depends(get_current_user),
) -> dict[str, Any]:
    """Manually link or update an email account for the user (supports dev & enterprise keys)."""
    from backend.core.config import settings
    account_service = get_user_email_account_service()

    # Use provided tokens or fall back to system env if requested
    refresh_token = body.refresh_token or settings.gmail_refresh_token or ""
    access_token = body.access_token or settings.gmail_access_token or ""

    account = UserEmailAccount(
        id="",
        user_id=user.subject,
        tenant_id=user.tenant_id or "enterprise-tenant",
        email_address=body.email_address,
        display_name=body.display_name or user.name or "Enterprise User",
        provider="google",
        access_token=access_token,
        refresh_token=refresh_token,
        token_expires_at=time.time() + 3600 if access_token else 0.0,
        scopes="gmail.readonly,email,profile",
        is_active=True,
    )
    saved = account_service.save_account(account)

    return {
        "status": "connected",
        "account": {
            "id": saved.id,
            "email_address": saved.email_address,
            "display_name": saved.display_name,
            "provider": saved.provider,
            "connected_at": saved.connected_at,
        },
    }
