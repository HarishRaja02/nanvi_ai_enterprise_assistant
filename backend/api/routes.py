from fastapi import APIRouter, Depends

from backend.security.dependencies import get_current_user
from backend.security.models import UserIdentity

router = APIRouter()


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/v1/health")
async def health_v1() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/live")
async def liveness() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/ready")
async def readiness() -> dict[str, str]:
    return {"status": "ready"}


@router.get("/auth/me")
async def current_user(user: UserIdentity = Depends(get_current_user)) -> UserIdentity:
    return user


@router.get("/auth/google/callback")
async def google_auth_callback(code: str, state: str | None = None):
    """Handle direct Google OAuth redirect to backend, save mailbox tokens, and redirect to frontend."""
    import time
    from fastapi.responses import RedirectResponse
    from backend.core.config import settings
    from backend.integrations.email.oauth import get_google_oauth_service
    from backend.integrations.email.user_account_service import UserEmailAccount, get_user_email_account_service

    oauth = get_google_oauth_service()
    account_service = get_user_email_account_service()

    redirect_uri = settings.google_redirect_uri or "http://127.0.0.1:8000/api/auth/google/callback"

    state_data = oauth.decode_state(state) if state else {}
    user_id = state_data.get("uid") or "ceo"
    tenant_id = state_data.get("tid") or "enterprise-tenant"

    token_data = oauth.exchange_code(code, redirect_uri=redirect_uri)
    access_token = token_data.get("access_token", "")
    refresh_token = token_data.get("refresh_token", "")
    expires_in = token_data.get("expires_in", 3600)

    userinfo = oauth.fetch_userinfo(access_token) if access_token else {}
    email_address = userinfo.get("email") or f"{user_id}@gmail.com"
    display_name = userinfo.get("name") or "Google Workspace User"
    avatar_url = userinfo.get("picture")

    if not refresh_token:
        existing = account_service.get_active_account(user_id)
        if existing and existing.refresh_token:
            refresh_token = existing.refresh_token

    account = UserEmailAccount(
        id="",
        user_id=user_id,
        tenant_id=tenant_id,
        email_address=email_address,
        display_name=display_name,
        provider="google",
        access_token=access_token,
        refresh_token=refresh_token,
        token_expires_at=time.time() + expires_in,
        scopes=token_data.get("scope", "gmail.readonly"),
        avatar_url=avatar_url,
        is_active=True,
    )
    account_service.save_account(account)

    frontend_url = "http://127.0.0.1:5173/?mailbox_connected=true"
    return RedirectResponse(url=frontend_url)

