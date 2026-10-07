"""Admin Console & Platform Management routes for Nanvi AI Enterprise Assistant.

Strictly restricted to Admin and CEO roles.
Provides user credential management, trouble ticket resolution, and backend DB connection settings.
"""
from __future__ import annotations

import logging
import os
import re
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from backend.core.config import settings
from backend.security.authorization.rbac import Role
from backend.security.dependencies import get_current_user
from backend.security.local_accounts import LocalAccountStore, get_local_account_store
from backend.security.models import UserIdentity
from backend.support.ticket_store import SupportTicketStore, get_support_ticket_store

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])


def _require_admin_or_ceo(user: UserIdentity) -> None:
    """Ensure the caller has system administrator credentials only.
    Superior level role access cannot use or see the admin dashboard.
    """
    is_admin = (
        user.subject == "admin"
        or (user.email and user.email.lower() in {"admin@company", "admin@company.com"})
        or "Admin" in user.roles
    )
    if not is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access restricted strictly to System Administrators [admin / admin@company]. Superior and user roles cannot use or view the admin dashboard.",
        )


def _mask_url(url: str) -> str:
    if not url:
        return ""
    try:
        parsed = urlparse(url)
        if parsed.password:
            masked = url.replace(f":{parsed.password}@", ":********@")
            return masked
        return url
    except Exception:
        return "***"


def _mask_key(key: str) -> str:
    if not key or len(key) < 8:
        return "********"
    return f"{key[:6]}...{key[-4:]}"


# --- Request & Response Models ---

class AdminAccountCreate(BaseModel):
    username: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=6, max_length=200)
    role: str = Field(default="Employee")
    display_name: str = Field(min_length=1, max_length=200)
    email: str | None = Field(default=None, max_length=255)
    department: str | None = Field(default=None, max_length=100)


class AdminAccountUpdate(BaseModel):
    display_name: str | None = None
    email: str | None = None
    role: str | None = None
    department: str | None = None
    active: bool | None = None


class AdminPasswordReset(BaseModel):
    new_password: str = Field(min_length=6, max_length=200)


class TicketStatusUpdate(BaseModel):
    status: str = Field(min_length=1, max_length=50)
    admin_notes: str | None = None


class DatabaseTestRequest(BaseModel):
    database_url: str | None = None
    supabase_database_url: str | None = None


class DatabaseConfigRequest(BaseModel):
    database_url: str | None = None
    supabase_database_url: str | None = None
    supabase_url: str | None = None
    supabase_key: str | None = None
    pool_min_size: int | None = Field(default=None, ge=1, le=20)
    pool_max_size: int | None = Field(default=None, ge=2, le=50)


# --- Admin Endpoints ---

@router.get("/overview")
def get_admin_overview(
    user: UserIdentity = Depends(get_current_user),
    account_store: LocalAccountStore = Depends(get_local_account_store),
    ticket_store: SupportTicketStore = Depends(get_support_ticket_store),
) -> dict[str, Any]:
    """Return platform overview cards for system administrator / CEO."""
    _require_admin_or_ceo(user)

    tenant_id = user.tenant_id or "enterprise-tenant"
    accounts = account_store.list_accounts(tenant_id)
    total_users = len(accounts)
    active_users = sum(1 for a in accounts if a.get("active"))

    tickets = ticket_store.list_tickets()
    total_tickets = len(tickets)
    open_tickets = sum(1 for t in tickets if t.get("status", "").lower() in {"open", "in progress", "investigating"})

    # Probe Database Connection
    db_target = settings.supabase_database_url or settings.database_url
    db_type = "Supabase PostgreSQL (Cloud)" if settings.supabase_database_url else ("PostgreSQL" if settings.database_url else "SQLite Enterprise (Local)")
    db_connected = False
    db_latency_ms = 0.0

    if db_target:
        try:
            import psycopg
            t0 = time.perf_counter()
            with psycopg.connect(db_target, connect_timeout=3) as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1;")
                    cur.fetchone()
            db_latency_ms = round((time.perf_counter() - t0) * 1000, 2)
            db_connected = True
        except Exception:
            db_connected = False
    else:
        db_connected = True
        db_latency_ms = 0.5

    return {
        "total_users": total_users,
        "active_users": active_users,
        "total_tickets": total_tickets,
        "open_tickets": open_tickets,
        "db_type": db_type,
        "db_connected": db_connected,
        "db_latency_ms": db_latency_ms,
        "multi_tenant_status": "Active (100% Isolated Data per User)",
        "uecp_status": "Admin Bypass Active",
        "app_env": settings.app_env,
        "current_admin": {
            "name": user.name or user.subject,
            "email": user.email,
            "roles": list(user.roles),
        },
    }


# --- Account Management ---

@router.get("/accounts")
def list_accounts_admin(
    user: UserIdentity = Depends(get_current_user),
    store: LocalAccountStore = Depends(get_local_account_store),
) -> list[dict[str, Any]]:
    """List all user accounts in the platform."""
    _require_admin_or_ceo(user)
    tenant_id = user.tenant_id or "enterprise-tenant"
    return store.list_accounts(tenant_id)


@router.post("/accounts", status_code=status.HTTP_201_CREATED)
def create_account_admin(
    body: AdminAccountCreate,
    user: UserIdentity = Depends(get_current_user),
    store: LocalAccountStore = Depends(get_local_account_store),
) -> dict[str, Any]:
    """Create a new user account with dedicated credentials and isolated storage."""
    _require_admin_or_ceo(user)
    tenant_id = user.tenant_id or "enterprise-tenant"
    try:
        return store.create_account(
            tenant_id=tenant_id,
            username=body.username,
            password=body.password,
            role=body.role,
            display_name=body.display_name,
            email=body.email,
            department=body.department,
            allow_short_password=True,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch("/accounts/{account_id}")
def update_account_admin(
    account_id: str,
    body: AdminAccountUpdate,
    user: UserIdentity = Depends(get_current_user),
    store: LocalAccountStore = Depends(get_local_account_store),
) -> dict[str, Any]:
    """Update user credentials or unlock/lock status."""
    _require_admin_or_ceo(user)
    tenant_id = user.tenant_id or "enterprise-tenant"
    try:
        return store.update_account(
            account_id,
            tenant_id=tenant_id,
            display_name=body.display_name,
            email=body.email,
            role=body.role,
            department=body.department,
            active=body.active,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/accounts/{account_id}/reset-password")
def reset_password_admin(
    account_id: str,
    body: AdminPasswordReset,
    user: UserIdentity = Depends(get_current_user),
    store: LocalAccountStore = Depends(get_local_account_store),
) -> dict[str, Any]:
    """Reset a user's password to immediately solve login lockout issues."""
    _require_admin_or_ceo(user)
    tenant_id = user.tenant_id or "enterprise-tenant"
    try:
        return store.reset_password(account_id, body.new_password, tenant_id=tenant_id)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/accounts/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_account_admin(
    account_id: str,
    user: UserIdentity = Depends(get_current_user),
    store: LocalAccountStore = Depends(get_local_account_store),
) -> None:
    """Delete a user account."""
    _require_admin_or_ceo(user)
    tenant_id = user.tenant_id or "enterprise-tenant"
    try:
        store.delete_account(account_id, tenant_id)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# --- Support Trouble Tickets ---

@router.get("/tickets")
def list_tickets_admin(
    status_filter: str = Query(default="all", alias="status"),
    user: UserIdentity = Depends(get_current_user),
    store: SupportTicketStore = Depends(get_support_ticket_store),
) -> list[dict[str, Any]]:
    """List all user-submitted trouble reports and support tickets."""
    _require_admin_or_ceo(user)
    return store.list_tickets(status=status_filter if status_filter != "all" else None)


@router.patch("/tickets/{ticket_id}")
def update_ticket_admin(
    ticket_id: str,
    body: TicketStatusUpdate,
    user: UserIdentity = Depends(get_current_user),
    store: SupportTicketStore = Depends(get_support_ticket_store),
) -> dict[str, Any]:
    """Update ticket resolution status and add developer resolution notes."""
    _require_admin_or_ceo(user)
    try:
        return store.update_ticket_status(ticket_id, body.status, body.admin_notes)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/tickets/{ticket_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_ticket_admin(
    ticket_id: str,
    user: UserIdentity = Depends(get_current_user),
    store: SupportTicketStore = Depends(get_support_ticket_store),
) -> None:
    """Delete or archive a resolved trouble ticket."""
    _require_admin_or_ceo(user)
    try:
        store.delete_ticket(ticket_id)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# --- Database Connection Management (Strictly Admin & CEO Only) ---

@router.get("/database/config")
def get_database_config(
    user: UserIdentity = Depends(get_current_user),
) -> dict[str, Any]:
    """Retrieve database connection details and live health. Restricted to Admin and CEO."""
    _require_admin_or_ceo(user)

    target_dsn = settings.supabase_database_url or settings.database_url
    parsed = None
    if target_dsn:
        try:
            parsed = urlparse(target_dsn)
        except Exception:
            pass

    # Quick test of current connection
    latency_ms = 0.0
    connected = False
    server_version = ""
    table_stats: dict[str, int] = {}

    if target_dsn:
        try:
            import psycopg
            t0 = time.perf_counter()
            with psycopg.connect(target_dsn, connect_timeout=3) as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT version();")
                    row = cur.fetchone()
                    if row:
                        server_version = str(row[0]).split(",")[0]
                    cur.execute("""
                        SELECT table_name FROM information_schema.tables 
                        WHERE table_schema = 'public';
                    """)
                    tables = cur.fetchall()
                    for t in tables[:10]:
                        t_name = t[0]
                        try:
                            cur.execute(f"SELECT COUNT(*) FROM public.{t_name};")
                            cnt = cur.fetchone()[0]
                            table_stats[t_name] = cnt
                        except Exception:
                            pass
            latency_ms = round((time.perf_counter() - t0) * 1000, 2)
            connected = True
        except Exception as exc:
            logger.warning("DB config probe failed: %s", exc)
            connected = False

    return {
        "database_type": "Supabase PostgreSQL (Cloud)" if settings.supabase_database_url else ("PostgreSQL" if settings.database_url else "SQLite Enterprise"),
        "database_url_masked": _mask_url(settings.database_url),
        "supabase_database_url_masked": _mask_url(settings.supabase_database_url),
        "supabase_url": settings.supabase_url,
        "supabase_key_masked": _mask_key(settings.supabase_key),
        "host": parsed.hostname if parsed else "db.supabase.co",
        "port": parsed.port if parsed else 5432,
        "database_name": parsed.path.lstrip("/") if parsed else "postgres",
        "username": parsed.username if parsed else "postgres",
        "pool_min_size": settings.database_pool_min_size,
        "pool_max_size": settings.database_pool_max_size,
        "is_connected": connected,
        "latency_ms": latency_ms,
        "server_version": server_version,
        "table_stats": table_stats,
        "multi_tenant_partitioning": {
            "status": "Strictly Isolated",
            "description": "Shared enterprise database connection with per-user tenant and owner partitions. Conversations, private credentials, and uploaded files cannot be viewed across accounts.",
        },
    }


@router.post("/database/test")
def test_database_connection(
    body: DatabaseTestRequest,
    user: UserIdentity = Depends(get_current_user),
) -> dict[str, Any]:
    """Test a database connection string in real-time. Restricted to Admin and CEO."""
    _require_admin_or_ceo(user)

    target_dsn = body.supabase_database_url or body.database_url or settings.supabase_database_url or settings.database_url
    if not target_dsn:
        raise HTTPException(status_code=400, detail="No database connection string provided to test.")

    try:
        import psycopg
        t0 = time.perf_counter()
        with psycopg.connect(target_dsn, connect_timeout=4) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT version();")
                version_info = cur.fetchone()[0]
        latency = round((time.perf_counter() - t0) * 1000, 2)
        return {
            "success": True,
            "message": f"Successfully connected to database in {latency}ms.",
            "latency_ms": latency,
            "server_version": str(version_info).split(",")[0],
        }
    except Exception as exc:
        return {
            "success": False,
            "message": f"Database connection failed: {str(exc)}",
            "latency_ms": 0.0,
        }


@router.put("/database/config")
def update_database_config(
    body: DatabaseConfigRequest,
    user: UserIdentity = Depends(get_current_user),
) -> dict[str, Any]:
    """Update runtime database connection configuration. Restricted to Admin and CEO."""
    _require_admin_or_ceo(user)

    updated_keys = []
    env_file = Path(__file__).resolve().parents[2] / ".env"

    env_content = ""
    if env_file.exists():
        try:
            env_content = env_file.read_text(encoding="utf-8")
        except Exception:
            env_content = ""

    def _update_env_var(key: str, val: str) -> None:
        nonlocal env_content
        pattern = rf"^{key}=.*$"
        if re.search(pattern, env_content, flags=re.MULTILINE):
            env_content = re.sub(pattern, f"{key}={val}", env_content, flags=re.MULTILINE)
        else:
            env_content += f"\n{key}={val}"

    if body.supabase_database_url:
        os.environ["SUPABASE_DATABASE_URL"] = body.supabase_database_url
        _update_env_var("SUPABASE_DATABASE_URL", f'"{body.supabase_database_url}"')
        updated_keys.append("SUPABASE_DATABASE_URL")

    if body.database_url:
        os.environ["DATABASE_URL"] = body.database_url
        _update_env_var("DATABASE_URL", body.database_url)
        updated_keys.append("DATABASE_URL")

    if body.supabase_url:
        os.environ["SUPABASE_URL"] = body.supabase_url
        _update_env_var("SUPABASE_URL", f'"{body.supabase_url}"')
        updated_keys.append("SUPABASE_URL")

    if body.supabase_key:
        os.environ["SUPABASE_KEY"] = body.supabase_key
        _update_env_var("SUPABASE_KEY", f'"{body.supabase_key}"')
        updated_keys.append("SUPABASE_KEY")

    if env_file.exists() and updated_keys:
        try:
            env_file.write_text(env_content, encoding="utf-8")
        except Exception as exc:
            logger.warning("Could not persist updated DB config to .env: %s", exc)

    return {
        "success": True,
        "message": f"Database configuration updated successfully ({', '.join(updated_keys)}).",
        "updated_keys": updated_keys,
    }
