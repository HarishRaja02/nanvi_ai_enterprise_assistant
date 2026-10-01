from __future__ import annotations

import time
from datetime import datetime
from typing import Literal

import jwt
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from backend.core.config import settings
from backend.security.authorization.permissions import Permission
from backend.security.authorization.rbac import Role, has_permission
from backend.security.dependencies import get_current_user
from backend.security.local_accounts import LocalAccountStore, get_local_account_store
from backend.security.models import UserIdentity

router = APIRouter(prefix="/auth", tags=["authentication"])

LocalRole = Literal["Superior", "Supervisor", "Project Engineer", "Employee"]
ADMINISTRATIVE_ROLES = {Role.SUPERIOR, Role.SUPERVISOR, Role.CEO, Role.FINANCE}
SUPERVISOR_MANAGED_ROLES = {Role.PROJECT_ENGINEER.value, Role.EMPLOYEE.value}


class LocalLoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=1, max_length=200)
    role: LocalRole


class AccountCreateRequest(BaseModel):
    username: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=12, max_length=200)
    role: LocalRole
    display_name: str = Field(min_length=1, max_length=200)
    email: str | None = Field(default=None, max_length=255)
    department: str | None = Field(default=None, max_length=100)


class LocalAccountResponse(BaseModel):
    id: str
    username: str
    role: str
    display_name: str
    email: str | None = None
    department: str | None = None
    active: bool
    # SQLite stores this as text while PostgreSQL returns a datetime object.
    # Accept both so account create/list responses serialize on either backend.
    created_at: datetime | str | None = None


def _ensure_local_auth_enabled() -> None:
    if not settings.local_auth_enabled:
        raise HTTPException(status_code=404, detail="Local sign-in is not enabled.")
    if not settings.jwt_secret:
        raise HTTPException(status_code=503, detail="Local sign-in is not configured.")


def _require_account_manager(user: UserIdentity) -> bool:
    if not any(has_permission(role, Permission.USER_MANAGE.value) for role in user.roles):
        raise HTTPException(status_code=403, detail="You are not allowed to manage user accounts.")
    return bool(user.roles & ADMINISTRATIVE_ROLES)


@router.post("/login")
def local_login(body: LocalLoginRequest, store: LocalAccountStore = Depends(get_local_account_store)) -> dict[str, object]:
    _ensure_local_auth_enabled()
    account = store.authenticate(body.username, body.password, body.role, settings.local_auth_tenant_id)
    if not account:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User ID, password, or selected role is incorrect.")

    now = int(time.time())
    payload = {
        "sub": account["id"],
        "iss": "nanvi-local",
        "aud": "nanvi-local",
        "iat": now,
        "exp": now + 8 * 60 * 60,
        "name": account["display_name"],
        "email": account.get("email"),
        "tenant_id": settings.local_auth_tenant_id,
        "department": account.get("department"),
        "roles": [account["role"]],
    }
    return {
        "access_token": jwt.encode(payload, settings.jwt_secret, algorithm="HS256"),
        "token_type": "bearer",
        "expires_in": 8 * 60 * 60,
    }


@router.get("/accounts", response_model=list[LocalAccountResponse])
def list_local_accounts(
    user: UserIdentity = Depends(get_current_user),
    store: LocalAccountStore = Depends(get_local_account_store),
) -> list[LocalAccountResponse]:
    _require_account_manager(user)
    accounts = store.list_accounts(user.tenant_id or "enterprise-tenant")
    if not user.roles & {Role.SUPERIOR, Role.CEO}:
        accounts = [account for account in accounts if account["role"] in SUPERVISOR_MANAGED_ROLES]
    return [LocalAccountResponse(**account) for account in accounts]


@router.post("/accounts", response_model=LocalAccountResponse, status_code=status.HTTP_201_CREATED)
def create_local_account(
    body: AccountCreateRequest,
    user: UserIdentity = Depends(get_current_user),
    store: LocalAccountStore = Depends(get_local_account_store),
) -> LocalAccountResponse:
    is_superior = _require_account_manager(user) and bool(user.roles & {Role.SUPERIOR, Role.CEO})
    if not is_superior and body.role not in SUPERVISOR_MANAGED_ROLES:
        raise HTTPException(status_code=403, detail="Supervisors can create Project Engineer and Employee accounts only.")
    try:
        account = store.create_account(
            tenant_id=user.tenant_id or "enterprise-tenant",
            username=body.username,
            password=body.password,
            role=body.role,
            display_name=body.display_name,
            email=body.email,
            department=body.department,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return LocalAccountResponse(**account)


@router.delete("/accounts/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_local_account(
    account_id: str,
    user: UserIdentity = Depends(get_current_user),
    store: LocalAccountStore = Depends(get_local_account_store),
) -> None:
    is_superior = _require_account_manager(user) and bool(user.roles & {Role.SUPERIOR, Role.CEO})
    tenant_id = user.tenant_id or "enterprise-tenant"
    try:
        target = store.get_account(account_id, tenant_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    if not is_superior and target["role"] not in SUPERVISOR_MANAGED_ROLES:
        raise HTTPException(status_code=403, detail="Supervisors can remove Project Engineer and Employee accounts only.")
    if account_id == user.subject:
        raise HTTPException(status_code=400, detail="You cannot remove the account you are currently using.")
    if target["role"] == Role.SUPERIOR.value and store.count_role(tenant_id, Role.SUPERIOR.value) <= 1:
        raise HTTPException(status_code=400, detail="At least one Superior account must remain active.")

    store.delete_account(account_id, tenant_id)
