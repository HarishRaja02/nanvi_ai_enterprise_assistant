"""FastAPI routes for Universal Connections Hub."""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status

from backend.connections.authz import can_view_audit
from backend.connections.base import (
    AmbiguousConnection,
    ConnectionError as HubConnectionError,
    InvalidCredentials,
    OAuthDenied,
    OAuthExpired,
    ProviderUnavailable,
    SSRFBlocked,
    TlsError,
    Unreachable,
)
from backend.connections.manager import ConnectionManager, get_connection_manager
from backend.connections.registry import ProviderRegistry, get_provider_registry
from backend.connections.schemas import (
    ConnectionListResponse,
    ConnectionPublic,
    CreateConnectionRequest,
    ProviderListResponse,
    ProviderPublic,
    TestConnectionResponse,
    UpdateConnectionRequest,
    ValidateConnectionRequest,
)
from backend.security.dependencies import get_current_user
from backend.security.models import UserIdentity

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/connections", tags=["connections"])


def _handle_error(exc: Exception) -> HTTPException:
    msg = getattr(exc, "friendly_message", str(exc))
    if isinstance(exc, (InvalidCredentials, OAuthDenied)):
        return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=msg)
    if isinstance(exc, (ProviderUnavailable, HubConnectionError)) and "not found" in str(exc).lower():
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg)
    if isinstance(exc, (SSRFBlocked, OAuthExpired, AmbiguousConnection)):
        return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)
    if isinstance(exc, (Unreachable, TlsError)):
        return HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=msg)
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)


# ── Provider Catalog ──────────────────────────────────────────

@router.get("/providers", response_model=ProviderListResponse)
def list_providers(
    registry: ProviderRegistry = Depends(get_provider_registry),
) -> ProviderListResponse:
    """Return the provider catalog with dynamic forms and availability status."""
    return ProviderListResponse(providers=registry.list_all())


@router.get("/categories", response_model=list[str])
def list_categories(
    registry: ProviderRegistry = Depends(get_provider_registry),
) -> list[str]:
    """Return unique categories across all providers."""
    return registry.get_categories()


# ── Connection Management ─────────────────────────────────────

@router.get("", response_model=ConnectionListResponse)
def list_connections(
    provider: str | None = Query(default=None),
    scope: str | None = Query(default=None),
    status: str | None = Query(default=None),
    q: str | None = Query(default=None),
    user: UserIdentity = Depends(get_current_user),
    manager: ConnectionManager = Depends(get_connection_manager),
) -> ConnectionListResponse:
    """List connections accessible to the current user."""
    conns = manager.list_connections(
        user,
        provider=provider,
        scope=scope,
        status=status,
        query=q,
    )
    return ConnectionListResponse(connections=conns, total=len(conns))


@router.get("/{connection_id}", response_model=ConnectionPublic)
def get_connection(
    connection_id: str,
    user: UserIdentity = Depends(get_current_user),
    manager: ConnectionManager = Depends(get_connection_manager),
) -> ConnectionPublic:
    """Get connection details (without sensitive credentials)."""
    try:
        return manager.get_connection(connection_id, user)
    except Exception as exc:
        raise _handle_error(exc)


@router.post("", response_model=ConnectionPublic, status_code=status.HTTP_201_CREATED)
def create_connection(
    req: CreateConnectionRequest,
    user: UserIdentity = Depends(get_current_user),
    manager: ConnectionManager = Depends(get_connection_manager),
) -> ConnectionPublic:
    """Create a connection using credentials or form settings."""
    try:
        return manager.create_connection(user, req)
    except Exception as exc:
        raise _handle_error(exc)


@router.post("/validate", response_model=TestConnectionResponse)
def validate_connection(
    req: ValidateConnectionRequest,
    manager: ConnectionManager = Depends(get_connection_manager),
) -> TestConnectionResponse:
    """Test connection credentials before saving."""
    return manager.validate_credentials(req)


@router.post("/{connection_id}/test", response_model=TestConnectionResponse)
def test_existing_connection(
    connection_id: str,
    user: UserIdentity = Depends(get_current_user),
    manager: ConnectionManager = Depends(get_connection_manager),
) -> TestConnectionResponse:
    """Test an existing saved connection."""
    try:
        return manager.test_connection(connection_id, user)
    except Exception as exc:
        raise _handle_error(exc)


@router.patch("/{connection_id}", response_model=ConnectionPublic)
def update_connection(
    connection_id: str,
    req: UpdateConnectionRequest,
    user: UserIdentity = Depends(get_current_user),
    manager: ConnectionManager = Depends(get_connection_manager),
) -> ConnectionPublic:
    """Update connection name or non-secret configuration."""
    try:
        return manager.update_connection(connection_id, user, req)
    except Exception as exc:
        raise _handle_error(exc)


@router.delete("/{connection_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_connection(
    connection_id: str,
    user: UserIdentity = Depends(get_current_user),
    manager: ConnectionManager = Depends(get_connection_manager),
) -> None:
    """Disconnect and soft-delete a connection."""
    try:
        manager.delete_connection(connection_id, user)
    except Exception as exc:
        raise _handle_error(exc)


@router.get("/audit/events")
def list_audit_events(
    user: UserIdentity = Depends(get_current_user),
    manager: ConnectionManager = Depends(get_connection_manager),
) -> list[dict[str, Any]]:
    """List recent connection audit events (Admins and authorized users)."""
    if not can_view_audit(user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission denied: audit access requires administrator privileges.",
        )

    tenant_id = user.tenant_id or "enterprise-tenant"
    pg_sql = """
        SELECT id, tenant_id, actor_user_id, connection_id, provider, event, safe_metadata, ip, created_at
        FROM public.connection_audit_events
        WHERE tenant_id = %s
        ORDER BY created_at DESC LIMIT 100;
    """
    sqlite_sql = """
        SELECT id, tenant_id, actor_user_id, connection_id, provider, event, safe_metadata, ip, created_at
        FROM connection_audit_events
        WHERE tenant_id = ?
        ORDER BY created_at DESC LIMIT 100;
    """
    return manager._query(pg_sql, sqlite_sql, (tenant_id,))
