"""API routes for User Activity Logs.

Strictly restricted to 'Superior' and 'Admin' roles only.
Allows viewing all user chat queries and system-generated answers partitioned by date.
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from backend.logs.store import UserLogStore, get_user_log_store
from backend.security.dependencies import get_current_user
from backend.security.models import UserIdentity

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/logs", tags=["user_logs"])


def _require_superior_or_admin(user: UserIdentity) -> None:
    """Ensure caller has either Superior (CEO/Executive) or Admin credentials.

    Other roles (Supervisor, Project Engineer, Employee) are strictly forbidden.
    """
    roles_lower = {getattr(r, "value", str(r)).lower() for r in user.roles}
    is_admin = (
        user.subject.lower() == "admin"
        or (user.email and "admin@" in user.email.lower())
        or "admin" in roles_lower
    )
    is_superior = (
        "superior" in roles_lower
        or "ceo" in roles_lower
    )
    if not (is_admin or is_superior):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access restricted strictly to Superior and Admin roles.",
        )


class LogDatesResponse(BaseModel):
    dates: list[str]
    today: str


class LogItem(BaseModel):
    id: str
    user_id: str
    user_name: str
    user_role: str
    tenant_id: str
    query: str
    answer: str
    capability: str
    model: str
    created_at: str
    log_date: str


class LogsResponse(BaseModel):
    logs: list[LogItem]
    total: int
    date: str | None


@router.get("/dates", response_model=LogDatesResponse)
def get_log_dates(
    user: UserIdentity = Depends(get_current_user),
    store: UserLogStore = Depends(get_user_log_store),
):
    """Return distinct available dates formatted as DD-MM-YYYY (e.g. 02-11-2026)."""
    _require_superior_or_admin(user)
    dates = store.get_available_dates()
    today = dates[0] if dates else ""
    return LogDatesResponse(dates=dates, today=today)


@router.get("", response_model=LogsResponse)
def get_logs(
    date: str | None = Query(default=None, description="Date filter formatted as DD-MM-YYYY or 'all'"),
    search: str | None = Query(default=None, description="Optional search string"),
    user_id: str | None = Query(default=None, description="Filter by user id"),
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    user: UserIdentity = Depends(get_current_user),
    store: UserLogStore = Depends(get_user_log_store),
):
    """Retrieve user query and system answer logs for Superior and Admin roles."""
    _require_superior_or_admin(user)
    entries, total = store.get_logs(
        date=date,
        search=search,
        user_id=user_id,
        limit=limit,
        offset=offset,
    )
    return LogsResponse(
        logs=[LogItem(**e.to_dict()) for e in entries],
        total=total,
        date=date,
    )
