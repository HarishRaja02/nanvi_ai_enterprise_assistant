"""OAuth initiation and callback routes for Connections Hub."""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse

from backend.connections.manager import ConnectionManager, get_connection_manager
from backend.core.config import settings
from backend.security.dependencies import get_current_user
from backend.security.models import UserIdentity

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/connections/oauth", tags=["connections-oauth"])
auth_router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.get("/{provider}/authorize")
def start_oauth(
    provider: str,
    request: Request,
    scope_level: str = Query(default="user", pattern=r"^(user|organization)$"),
    redirect_after: str | None = Query(default=None),
    user: UserIdentity = Depends(get_current_user),
    manager: ConnectionManager = Depends(get_connection_manager),
) -> dict[str, str]:
    """Generate an authorization URL for OAuth provider."""
    base_url = settings.oauth_redirect_base_url or str(request.base_url).rstrip("/")
    redirect_uri = f"{base_url}/api/connections/oauth/{provider}/callback"

    try:
        auth_url = manager.start_oauth(
            provider_id=provider,
            user=user,
            redirect_uri=redirect_uri,
            redirect_after=redirect_after,
            scope_level=scope_level,
        )
        return {"authorization_url": auth_url}
    except Exception as exc:
        logger.error("OAuth start failed for %s: %s", provider, exc)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.get("/{provider}/callback")
def oauth_callback(
    provider: str,
    request: Request,
    code: str = Query(...),
    state: str = Query(...),
    manager: ConnectionManager = Depends(get_connection_manager),
) -> RedirectResponse:
    """Handle OAuth redirect callback from identity provider."""
    base_url = settings.oauth_redirect_base_url or str(request.base_url).rstrip("/")
    redirect_uri = f"{base_url}/api/connections/oauth/{provider}/callback"

    try:
        conn, redirect_after = manager.handle_oauth_callback(
            provider_id=provider,
            code=code,
            state=state,
            redirect_uri=redirect_uri,
        )
        target = redirect_after or "http://127.0.0.1:5173/settings?tab=connections"
        delimiter = "&" if "?" in target else "?"
        return RedirectResponse(url=f"{target}{delimiter}connected={provider}&status=success")
    except Exception as exc:
        logger.error("OAuth callback failed for %s: %s", provider, exc)
        target = "http://127.0.0.1:5173/settings?tab=connections"
        delimiter = "&" if "?" in target else "?"
        return RedirectResponse(url=f"{target}{delimiter}connected={provider}&status=error&error={str(exc)}")


# ── Top-level /api/auth/github routes ─────────────────────────

@auth_router.get("/github")
def github_auth_start(
    request: Request,
    scope_level: str = Query(default="user"),
    redirect_after: str | None = Query(default=None),
    user: UserIdentity = Depends(get_current_user),
    manager: ConnectionManager = Depends(get_connection_manager),
) -> RedirectResponse:
    """Initiate GitHub OAuth directly with redirect."""
    base_url = settings.oauth_redirect_base_url or str(request.base_url).rstrip("/")
    redirect_uri = f"{base_url}/api/auth/github/callback"

    auth_url = manager.start_oauth(
        provider_id="github",
        user=user,
        redirect_uri=redirect_uri,
        redirect_after=redirect_after,
        scope_level=scope_level,
    )
    return RedirectResponse(url=auth_url)


@auth_router.get("/github/callback")
def github_auth_callback(
    request: Request,
    code: str = Query(...),
    state: str = Query(...),
    manager: ConnectionManager = Depends(get_connection_manager),
) -> RedirectResponse:
    """Handle GitHub OAuth callback."""
    base_url = settings.oauth_redirect_base_url or str(request.base_url).rstrip("/")
    redirect_uri = f"{base_url}/api/auth/github/callback"

    try:
        conn, redirect_after = manager.handle_oauth_callback(
            provider_id="github",
            code=code,
            state=state,
            redirect_uri=redirect_uri,
        )
        target = redirect_after or "http://127.0.0.1:5173/settings?tab=connections"
        delimiter = "&" if "?" in target else "?"
        return RedirectResponse(url=f"{target}{delimiter}connected=github&status=success")
    except Exception as exc:
        logger.error("GitHub callback error: %s", exc)
        return RedirectResponse(url=f"http://127.0.0.1:5173/settings?tab=connections&connected=github&status=error&error={str(exc)}")


# ── Top-level /api/auth/google routes (backward-compatibility alias) ──

@auth_router.get("/google")
def google_auth_start(
    request: Request,
    scope_level: str = Query(default="user"),
    redirect_after: str | None = Query(default=None),
    user: UserIdentity = Depends(get_current_user),
    manager: ConnectionManager = Depends(get_connection_manager),
) -> RedirectResponse:
    """Initiate Google OAuth directly with redirect."""
    base_url = settings.oauth_redirect_base_url or str(request.base_url).rstrip("/")
    redirect_uri = f"{base_url}/api/auth/google/callback"

    auth_url = manager.start_oauth(
        provider_id="google",
        user=user,
        redirect_uri=redirect_uri,
        redirect_after=redirect_after,
        scope_level=scope_level,
    )
    return RedirectResponse(url=auth_url)


@auth_router.get("/google/callback")
def google_auth_callback(
    request: Request,
    code: str = Query(...),
    state: str = Query(...),
    manager: ConnectionManager = Depends(get_connection_manager),
) -> RedirectResponse:
    """Handle Google OAuth callback."""
    base_url = settings.oauth_redirect_base_url or str(request.base_url).rstrip("/")
    redirect_uri = f"{base_url}/api/auth/google/callback"

    try:
        conn, redirect_after = manager.handle_oauth_callback(
            provider_id="google",
            code=code,
            state=state,
            redirect_uri=redirect_uri,
        )
        target = redirect_after or "http://127.0.0.1:5173/settings?tab=connections"
        delimiter = "&" if "?" in target else "?"
        return RedirectResponse(url=f"{target}{delimiter}connected=google&status=success")
    except Exception as exc:
        logger.error("Google callback error: %s", exc)
        return RedirectResponse(url=f"http://127.0.0.1:5173/settings?tab=connections&connected=google&status=error&error={str(exc)}")

