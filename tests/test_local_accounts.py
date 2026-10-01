from __future__ import annotations

import pytest
import jwt
from fastapi import HTTPException

from types import SimpleNamespace

from backend.api import local_auth_routes
from backend.api.local_auth_routes import AccountCreateRequest, LocalLoginRequest, create_local_account, list_local_accounts, local_login
from backend.security.authorization.rbac import Role
from backend.security.local_accounts import LocalAccountStore
from backend.security.models import UserIdentity


@pytest.fixture
def account_store(tmp_path) -> LocalAccountStore:
    return LocalAccountStore(sqlite_path=tmp_path / "accounts.sqlite3")


def test_local_account_password_is_hashed_and_role_must_match(account_store: LocalAccountStore) -> None:
    account = account_store.create_account(
        tenant_id="tenant-a",
        username="project.user",
        password="a-long-and-unique-password",
        role=Role.PROJECT_ENGINEER.value,
        display_name="Project User",
        department="Engineering",
    )

    assert "password_hash" not in account
    assert "password_salt" not in account
    assert account_store.authenticate("PROJECT.USER", "a-long-and-unique-password", Role.PROJECT_ENGINEER.value, "tenant-a")
    assert account_store.authenticate("project.user", "wrong-password", Role.PROJECT_ENGINEER.value, "tenant-a") is None
    assert account_store.authenticate("project.user", "a-long-and-unique-password", Role.EMPLOYEE.value, "tenant-a") is None


def test_supervisor_can_manage_lower_roles_but_cannot_create_supervisor(
    account_store: LocalAccountStore,
) -> None:
    supervisor = UserIdentity(
        subject="supervisor-id",
        issuer="nanvi-local",
        tenant_id="tenant-a",
        roles=frozenset({Role.SUPERVISOR}),
    )
    created = create_local_account(
        AccountCreateRequest(
            username="engineer",
            password="a-unique-engineer-password",
            role=Role.PROJECT_ENGINEER.value,
            display_name="Engineer One",
        ),
        user=supervisor,
        store=account_store,
    )
    assert created.role == Role.PROJECT_ENGINEER.value

    with pytest.raises(HTTPException) as exc:
        create_local_account(
            AccountCreateRequest(
                username="new-supervisor",
                password="a-unique-supervisor-password",
                role=Role.SUPERVISOR.value,
                display_name="New Supervisor",
            ),
            user=supervisor,
            store=account_store,
        )
    assert exc.value.status_code == 403


def test_superior_can_list_accounts_without_secret_fields(account_store: LocalAccountStore) -> None:
    account_store.create_account(
        tenant_id="tenant-a",
        username="employee",
        password="an-employee-account-password",
        role=Role.EMPLOYEE.value,
        display_name="Employee One",
    )
    superior = UserIdentity(
        subject="superior-id",
        issuer="nanvi-local",
        tenant_id="tenant-a",
        roles=frozenset({Role.SUPERIOR}),
    )

    accounts = list_local_accounts(user=superior, store=account_store)

    assert [account.username for account in accounts] == ["employee"]
    assert not hasattr(accounts[0], "password_hash")


def test_local_login_signs_the_stored_role_and_rejects_a_mismatched_role(
    account_store: LocalAccountStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    account_store.create_account(
        tenant_id="enterprise-tenant",
        username="engineer",
        password="a-unique-engineer-password",
        role=Role.PROJECT_ENGINEER.value,
        display_name="Engineer One",
    )
    monkeypatch.setattr(
        local_auth_routes,
        "settings",
        SimpleNamespace(local_auth_enabled=True, jwt_secret="unit-test-secret-at-least-32-bytes-long", local_auth_tenant_id="enterprise-tenant"),
    )

    response = local_login(
        LocalLoginRequest(username="engineer", password="a-unique-engineer-password", role=Role.PROJECT_ENGINEER.value),
        store=account_store,
    )
    claims = jwt.decode(response["access_token"], "unit-test-secret-at-least-32-bytes-long", algorithms=["HS256"], audience="nanvi-local", issuer="nanvi-local")
    assert claims["roles"] == [Role.PROJECT_ENGINEER.value]
    assert claims["sub"]

    with pytest.raises(HTTPException) as exc:
        local_login(
            LocalLoginRequest(username="engineer", password="a-unique-engineer-password", role=Role.SUPERVISOR.value),
            store=account_store,
        )
    assert exc.value.status_code == 401