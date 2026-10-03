"""OAuth initiation and callback routes for Connections Hub."""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse

from backend.connections.base import OAuthDenied, OAuthExpired
from backend.connections.manager import ConnectionManager, get_connection_manager
from backend.core.config import settings
from backend.security.dependencies import get_current_user, get_optional_current_user
from backend.security.models import UserIdentity

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/connections/oauth", tags=["connections-oauth"])
auth_router = APIRouter(prefix="/api/auth", tags=["auth"])
auth_legacy_router = APIRouter(prefix="/auth", tags=["auth-legacy"])


def get_frontend_base_url(request: Request | None = None) -> str:
    """Get the frontend URL for redirecting users back to the UI.

    Seamlessly adapts to Vercel, cloud platforms, custom domains, and local dev.
    """
    if settings.oauth_redirect_base_url:
        return settings.oauth_redirect_base_url.rstrip("/")

    import os
    vercel_url = os.getenv("VERCEL_URL")
    if vercel_url:
        return f"https://{vercel_url.strip('/')}"

    if settings.cors_origins:
        return settings.cors_origins[0].rstrip("/")

    if request:
        origin = request.headers.get("origin") or request.headers.get("referer")
        if origin:
            from urllib.parse import urlparse
            p = urlparse(origin)
            if p.scheme and p.netloc:
                return f"{p.scheme}://{p.netloc}"

    return "http://localhost:5173"


def get_backend_callback_uri(request: Request, path: str, provider: str = "") -> str:
    """Resolve the OAuth callback redirect URI registered with the OAuth provider."""
    proto = request.headers.get("x-forwarded-proto") or request.url.scheme or "http"
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc

    # For Google: if explicitly configured in environment (e.g. GOOGLE_REDIRECT_URI), prefer it,
    # UNLESS the app is running in the cloud (Vercel/domain) and the setting is pointing to localhost.
    if provider == "google" and settings.google_redirect_uri:
        is_cloud_request = host and not any(h in host for h in ("localhost", "127.0.0.1", "0.0.0.0", "testserver"))
        is_configured_localhost = any(h in settings.google_redirect_uri for h in ("localhost", "127.0.0.1"))
        if not (is_cloud_request and is_configured_localhost):
            return settings.google_redirect_uri

    # Detect scheme and host (honoring proxy headers for Vercel/reverse proxies)
    if host:
        return f"{proto}://{host}{path}"

    base = str(request.base_url).rstrip("/")
    return f"{base}{path}"


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
    redirect_uri = get_backend_callback_uri(request, f"/api/connections/oauth/{provider}/callback", provider=provider)

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
    state: str | None = Query(default=None),
    current_user: UserIdentity | None = Depends(get_optional_current_user),
    manager: ConnectionManager = Depends(get_connection_manager),
) -> RedirectResponse:
    """Handle OAuth redirect callback from identity provider."""
    if not state:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing OAuth state parameter.",
        )
    redirect_uri = get_backend_callback_uri(request, f"/api/connections/oauth/{provider}/callback", provider=provider)
    frontend_base = get_frontend_base_url(request)

    try:
        conn, redirect_after = manager.handle_oauth_callback(
            provider_id=provider,
            code=code,
            state=state,
            redirect_uri=redirect_uri,
            expected_user_id=current_user.subject if current_user else None,
            expected_tenant_id=current_user.tenant_id if current_user else None,
        )
        target = redirect_after or f"{frontend_base}/?tab=connections"
        delimiter = "&" if "?" in target else "?"
        return RedirectResponse(url=f"{target}{delimiter}connected={provider}&status=success")
    except (OAuthDenied, OAuthExpired) as exc:
        logger.warning("OAuth denied/expired for %s: %s", provider, exc)
        msg = str(exc)
        if "replay" in msg.lower() or "consumed" in msg.lower() or "not issued to the authenticated user" in msg.lower() or "mismatch" in msg.lower():
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=msg)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)
    except Exception as exc:
        logger.error("OAuth callback failed for %s: %s", provider, exc)
        target = f"{frontend_base}/?tab=connections"
        delimiter = "&" if "?" in target else "?"
        return RedirectResponse(url=f"{target}{delimiter}connected={provider}&status=error&error={str(exc)}")


# ── Top-level /api/auth/github routes ─────────────────────────

@auth_router.get("/github")
@auth_legacy_router.get("/github")
def github_auth_start(
    request: Request,
    scope_level: str = Query(default="user"),
    redirect_after: str | None = Query(default=None),
    user: UserIdentity = Depends(get_current_user),
    manager: ConnectionManager = Depends(get_connection_manager),
) -> RedirectResponse:
    """Initiate GitHub OAuth directly with redirect."""
    redirect_uri = get_backend_callback_uri(request, "/api/auth/github/callback", provider="github")

    auth_url = manager.start_oauth(
        provider_id="github",
        user=user,
        redirect_uri=redirect_uri,
        redirect_after=redirect_after,
        scope_level=scope_level,
    )
    return RedirectResponse(url=auth_url)


@auth_router.get("/github/callback")
@auth_legacy_router.get("/github/callback")
def github_auth_callback(
    request: Request,
    code: str = Query(...),
    state: str | None = Query(default=None),
    current_user: UserIdentity | None = Depends(get_optional_current_user),
    manager: ConnectionManager = Depends(get_connection_manager),
) -> RedirectResponse:
    """Handle GitHub OAuth callback."""
    if not state:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing OAuth state parameter.",
        )
    redirect_uri = get_backend_callback_uri(request, "/api/auth/github/callback", provider="github")
    frontend_base = get_frontend_base_url(request)

    try:
        conn, redirect_after = manager.handle_oauth_callback(
            provider_id="github",
            code=code,
            state=state,
            redirect_uri=redirect_uri,
            expected_user_id=current_user.subject if current_user else None,
            expected_tenant_id=current_user.tenant_id if current_user else None,
        )
        target = redirect_after or f"{frontend_base}/?tab=connections"
        delimiter = "&" if "?" in target else "?"
        return RedirectResponse(url=f"{target}{delimiter}connected=github&status=success")
    except (OAuthDenied, OAuthExpired) as exc:
        logger.warning("GitHub OAuth denied/expired: %s", exc)
        msg = str(exc)
        if "replay" in msg.lower() or "consumed" in msg.lower() or "not issued to the authenticated user" in msg.lower() or "mismatch" in msg.lower():
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=msg)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)
    except Exception as exc:
        logger.error("GitHub callback error: %s", exc)
        return RedirectResponse(url=f"{frontend_base}/?tab=connections&connected=github&status=error&error={str(exc)}")


# ── Top-level /api/auth/google routes (backward-compatibility alias) ──

@auth_router.get("/google")
@auth_legacy_router.get("/google")
def google_auth_start(
    request: Request,
    scope_level: str = Query(default="user"),
    redirect_after: str | None = Query(default=None),
    user: UserIdentity = Depends(get_current_user),
    manager: ConnectionManager = Depends(get_connection_manager),
) -> RedirectResponse:
    """Initiate Google OAuth directly with redirect."""
    redirect_uri = get_backend_callback_uri(request, "/api/auth/google/callback", provider="google")

    auth_url = manager.start_oauth(
        provider_id="google",
        user=user,
        redirect_uri=redirect_uri,
        redirect_after=redirect_after,
        scope_level=scope_level,
    )
    return RedirectResponse(url=auth_url)


@auth_router.get("/google/callback")
@auth_legacy_router.get("/google/callback")
def google_auth_callback(
    request: Request,
    code: str = Query(...),
    state: str | None = Query(default=None),
    current_user: UserIdentity | None = Depends(get_optional_current_user),
    manager: ConnectionManager = Depends(get_connection_manager),
) -> RedirectResponse:
    """Handle Google OAuth callback."""
    if not state:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing OAuth state parameter.",
        )
    redirect_uri = get_backend_callback_uri(request, "/api/auth/google/callback", provider="google")
    frontend_base = get_frontend_base_url(request)

    try:
        conn, redirect_after = manager.handle_oauth_callback(
            provider_id="google",
            code=code,
            state=state,
            redirect_uri=redirect_uri,
            expected_user_id=current_user.subject if current_user else None,
            expected_tenant_id=current_user.tenant_id if current_user else None,
        )
        target = redirect_after or f"{frontend_base}/?tab=connections"
        delimiter = "&" if "?" in target else "?"
        return RedirectResponse(url=f"{target}{delimiter}connected=google&status=success")
    except (OAuthDenied, OAuthExpired) as exc:
        logger.warning("Google OAuth denied/expired: %s", exc)
        msg = str(exc)
        if "replay" in msg.lower() or "consumed" in msg.lower() or "not issued to the authenticated user" in msg.lower() or "mismatch" in msg.lower():
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=msg)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)
    except Exception as exc:
        logger.error("Google callback error: %s", exc)
        return RedirectResponse(url=f"{frontend_base}/?tab=connections&connected=google&status=error&error={str(exc)}")


