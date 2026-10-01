"""OAuth state tracking, lifecycle, and callback resolution."""
from __future__ import annotations

import json
import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from backend.connections.audit import ConnectionEventType
from backend.connections.authz import can_create_org_connection
from backend.connections.base import (
    Capability,
    ConnectionError,
    OAuthDenied,
    OAuthExpired,
    ProviderUnavailable,
    ScopeLevel,
)
from backend.connections.schemas import ConnectionPublic
from backend.security.models import UserIdentity

logger = logging.getLogger(__name__)


def start_oauth(
    manager: Any,
    provider_id: str,
    user: UserIdentity,
    redirect_uri: str,
    redirect_after: str | None = None,
    scope_level: str = "user",
) -> str:
    """Initiate OAuth flow: create signed state and return auth URL."""
    provider = manager._registry.get_provider(provider_id)
    if not provider:
        raise ProviderUnavailable(f"Provider not found: {provider_id}")

    if Capability.OAUTH not in provider.get_capabilities():
        raise ConnectionError(f"Provider '{provider_id}' does not support OAuth.")

    if scope_level == ScopeLevel.ORGANIZATION.value and not can_create_org_connection(user):
        raise ConnectionError("Permission denied: only administrators can create organization connections.")

    state = secrets.token_urlsafe(32)
    pkce_verifier = secrets.token_urlsafe(64)
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)
    tenant_id = user.tenant_id or "enterprise-tenant"

    pg_sql = """
        INSERT INTO public.oauth_states (
            state, user_id, tenant_id, provider, pkce_verifier, redirect_after, expires_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s);
    """
    sqlite_sql = """
        INSERT INTO oauth_states (
            state, user_id, tenant_id, provider, pkce_verifier, redirect_after, expires_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?);
    """
    manager._execute(
        pg_sql,
        sqlite_sql,
        (
            state,
            user.subject,
            tenant_id,
            provider_id,
            pkce_verifier,
            f"{redirect_after}|scope:{scope_level}" if redirect_after else f"scope:{scope_level}",
            expires_at.isoformat(),
        ),
    )

    auth_url = provider.get_authorization_url(
        user_id=user.subject,
        tenant_id=tenant_id,
        redirect_uri=redirect_uri,
        state=state,
        pkce_verifier=pkce_verifier,
    )
    return auth_url


def handle_oauth_callback(
    manager: Any,
    provider_id: str,
    code: str,
    state: str,
    redirect_uri: str,
    expected_user_id: str | None = None,
    expected_tenant_id: str | None = None,
) -> tuple[ConnectionPublic, str | None]:
    """Validate state, consume it, exchange code, store connection."""
    pg_sql = "SELECT * FROM public.oauth_states WHERE state = %s;"
    sqlite_sql = "SELECT * FROM oauth_states WHERE state = ?;"
    rows = manager._query(pg_sql, sqlite_sql, (state,))
    if not rows:
        raise OAuthDenied("Invalid or expired OAuth state.")

    state_row = rows[0]
    if state_row.get("consumed_at"):
        raise OAuthDenied("OAuth state has already been consumed (replay attack prevention).")

    expires_val = state_row.get("expires_at")
    if isinstance(expires_val, str):
        exp = datetime.fromisoformat(expires_val.replace("Z", "+00:00"))
    else:
        exp = expires_val
    if exp < datetime.now(timezone.utc):
        raise OAuthExpired("OAuth state has expired. Please restart authorization.")

    if expected_user_id and state_row.get("user_id") != expected_user_id:
        raise OAuthDenied("OAuth state was not issued to the authenticated user.")
    if expected_tenant_id and state_row.get("tenant_id") != expected_tenant_id:
        raise OAuthDenied("OAuth state tenant mismatch.")

    pg_consume = "UPDATE public.oauth_states SET consumed_at = NOW() WHERE state = %s;"
    sqlite_consume = "UPDATE oauth_states SET consumed_at = datetime('now') WHERE state = ?;"
    manager._execute(pg_consume, sqlite_consume, (state,))

    provider = manager._registry.get_provider(provider_id)
    if not provider:
        raise ProviderUnavailable(f"Provider not found: {provider_id}")

    pkce_verifier = state_row.get("pkce_verifier")
    auth_data = provider.handle_callback(
        code=code,
        state=state,
        redirect_uri=redirect_uri,
        pkce_verifier=pkce_verifier,
    )

    user_id = state_row["user_id"]
    tenant_id = state_row["tenant_id"]

    redirect_raw = state_row.get("redirect_after") or ""
    scope_level = "user"
    redirect_after = None
    if "|scope:" in redirect_raw:
        parts = redirect_raw.split("|scope:")
        redirect_after = parts[0] if parts[0] else None
        scope_level = parts[1]
    elif redirect_raw.startswith("scope:"):
        scope_level = redirect_raw.replace("scope:", "")
    elif redirect_raw:
        redirect_after = redirect_raw

    account_identifier = auth_data.get("account_identifier")
    display_name = auth_data.get("display_name") or f"{provider.get_metadata().name} ({account_identifier or user_id})"
    raw_credentials = auth_data.get("credentials", {})
    metadata_safe = auth_data.get("metadata_safe", {})
    granted_scopes = auth_data.get("granted_scopes", [])

    ciphertext, key_id = manager._encryption.encrypt_credentials(raw_credentials)
    owner_id = user_id if scope_level == ScopeLevel.USER.value else None

    pg_check = """
        SELECT id FROM public.connections
        WHERE tenant_id = %s AND provider = %s AND scope_level = %s
          AND COALESCE(owner_user_id, '') = COALESCE(%s, '')
          AND COALESCE(account_identifier, '') = COALESCE(%s, '')
          AND deleted_at IS NULL;
    """
    sqlite_check = """
        SELECT id FROM connections
        WHERE tenant_id = ? AND provider = ? AND scope_level = ?
          AND IFNULL(owner_user_id, '') = IFNULL(?, '')
          AND IFNULL(account_identifier, '') = IFNULL(?, '')
          AND deleted_at IS NULL;
    """
    existing = manager._query(pg_check, sqlite_check, (tenant_id, provider_id, scope_level, owner_id, account_identifier))

    if existing:
        conn_id = str(existing[0]["id"])
        pg_update = """
            UPDATE public.connections
            SET encrypted_credentials = %s, encryption_key_id = %s,
                granted_scopes = %s, metadata_safe = %s::jsonb,
                status = 'CONNECTED', status_reason = NULL,
                last_synced_at = NOW(), updated_at = NOW()
            WHERE id = %s;
        """
        sqlite_update = """
            UPDATE connections
            SET encrypted_credentials = ?, encryption_key_id = ?,
                granted_scopes = ?, metadata_safe = ?,
                status = 'CONNECTED', status_reason = NULL,
                last_synced_at = datetime('now'), updated_at = datetime('now')
            WHERE id = ?;
        """
        manager._execute(
            pg_update,
            sqlite_update,
            (
                ciphertext,
                key_id,
                granted_scopes if manager._use_postgres else json.dumps(granted_scopes),
                json.dumps(metadata_safe),
                conn_id,
            ),
        )
        manager._audit.record(
            ConnectionEventType.OAUTH_REAUTHORIZED,
            tenant_id=tenant_id,
            actor_user_id=user_id,
            connection_id=conn_id,
            provider=provider_id,
            safe_metadata={"account_identifier": account_identifier},
        )
    else:
        conn_id = str(uuid.uuid4())
        pg_ins = """
            INSERT INTO public.connections (
                id, tenant_id, owner_user_id, scope_level, provider, display_name,
                account_identifier, credential_type, encrypted_credentials, encryption_key_id,
                granted_scopes, metadata_safe, status, status_reason, last_synced_at,
                created_by, created_at, updated_at
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, 'oauth2', %s, %s, %s, %s::jsonb, 'CONNECTED', NULL, NOW(), %s, NOW(), NOW()
            );
        """
        sqlite_ins = """
            INSERT INTO connections (
                id, tenant_id, owner_user_id, scope_level, provider, display_name,
                account_identifier, credential_type, encrypted_credentials, encryption_key_id,
                granted_scopes, metadata_safe, status, status_reason, last_synced_at,
                created_by, created_at, updated_at
            ) VALUES (
                ?, ?, ?, ?, ?, ?, ?, 'oauth2', ?, ?, ?, ?, 'CONNECTED', NULL, datetime('now'), ?, datetime('now'), datetime('now')
            );
        """
        manager._execute(
            pg_ins,
            sqlite_ins,
            (
                conn_id,
                tenant_id,
                owner_id,
                scope_level,
                provider_id,
                display_name,
                account_identifier,
                ciphertext,
                key_id,
                granted_scopes if manager._use_postgres else json.dumps(granted_scopes),
                json.dumps(metadata_safe),
                user_id,
            ),
        )
        manager._audit.record(
            ConnectionEventType.OAUTH_CONNECTED,
            tenant_id=tenant_id,
            actor_user_id=user_id,
            connection_id=conn_id,
            provider=provider_id,
            safe_metadata={"account_identifier": account_identifier},
        )

    if provider_id == "google":
        try:
            from backend.integrations.email.user_account_service import UserEmailAccount, get_user_email_account_service
            account_svc = get_user_email_account_service()
            email_acc = UserEmailAccount(
                id="",
                user_id=user_id,
                tenant_id=tenant_id,
                email_address=account_identifier or f"{user_id}@gmail.com",
                display_name=display_name,
                provider="google",
                access_token=raw_credentials.get("access_token", ""),
                refresh_token=raw_credentials.get("refresh_token", ""),
                token_expires_at=float(raw_credentials.get("token_expires_at", 0.0) or 0.0),
                scopes=" ".join(granted_scopes) if isinstance(granted_scopes, list) else str(granted_scopes),
                avatar_url=metadata_safe.get("avatar_url"),
                is_active=True,
            )
            account_svc.save_account(email_acc)
        except Exception as exc:
            logger.warning("Could not sync email account in handle_oauth_callback: %s", exc)

    from backend.security.authorization.rbac import Role
    mock_user = UserIdentity(
        subject=user_id,
        issuer="internal",
        email=account_identifier or "",
        name="",
        tenant_id=tenant_id,
        department="Operations",
        roles=frozenset({Role.EMPLOYEE, Role.IT_ADMIN}),
    )
    return manager.get_connection(conn_id, mock_user), redirect_after
