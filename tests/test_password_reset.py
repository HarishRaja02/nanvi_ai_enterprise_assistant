from __future__ import annotations

import time
import pytest
from fastapi import HTTPException
from types import SimpleNamespace

from backend.api import local_auth_routes
from backend.api.local_auth_routes import (
    ForgotPasswordRequest,
    RegisterRequest,
    ResetPasswordWithTokenRequest,
    forgot_password,
    register_account,
    reset_password_with_token,
    verify_reset_token,
)
from backend.security.authorization.rbac import Role
from backend.security.local_accounts import LocalAccountStore


@pytest.fixture
def account_store(tmp_path) -> LocalAccountStore:
    return LocalAccountStore(sqlite_path=tmp_path / "reset_test_accounts.sqlite3")


def test_registration_requires_valid_email(account_store: LocalAccountStore) -> None:
    # Invalid email format should be rejected
    with pytest.raises(HTTPException) as exc:
        register_account(
            RegisterRequest(
                username="testuser",
                email="not-an-email",
                password="securePassword123!",
                display_name="Test User",
            ),
            store=account_store,
        )
    assert exc.value.status_code == 400
    assert "email" in str(exc.value.detail).lower()

    # Valid registration succeeds
    created = register_account(
        RegisterRequest(
            username="testuser",
            email="testuser@company.com",
            password="securePassword123!",
            display_name="Test User",
        ),
        store=account_store,
    )
    assert created.username == "testuser"
    assert created.email == "testuser@company.com"

    # Duplicate email should be rejected
    with pytest.raises(HTTPException) as exc2:
        register_account(
            RegisterRequest(
                username="different_user",
                email="testuser@company.com",
                password="anotherPassword123!",
                display_name="Another User",
            ),
            store=account_store,
        )
    assert exc2.value.status_code == 400
    assert "already exists" in str(exc2.value.detail).lower()


def test_forgot_password_and_reset_link_lifecycle(
    account_store: LocalAccountStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        local_auth_routes,
        "settings",
        SimpleNamespace(
            local_auth_enabled=True,
            jwt_secret="test-secret-at-least-32-bytes-long",
            local_auth_tenant_id="enterprise-tenant",
            frontend_url="http://localhost:5173",
            is_development=True,
            is_demo=False,
            smtp_host="",
        ),
    )

    # 1. Create target account
    account_store.create_account(
        tenant_id="enterprise-tenant",
        username="maya.nair",
        password="InitialPassword2026!",
        role=Role.PROJECT_ENGINEER.value,
        display_name="Maya Nair",
        email="maya.nair@company.com",
        require_email=True,
    )

    # 2. Mismatched email should not generate a dev reset link
    resp_mismatch = forgot_password(
        ForgotPasswordRequest(username="maya.nair", email="wrong.email@company.com"),
        store=account_store,
    )
    assert "dev_reset_link" not in resp_mismatch

    # 3. Correct username and email generates a valid reset token
    resp_correct = forgot_password(
        ForgotPasswordRequest(username="maya.nair", email="maya.nair@company.com"),
        store=account_store,
    )
    assert "dev_reset_link" in resp_correct
    reset_link = resp_correct["dev_reset_link"]
    assert "token=" in reset_link
    token = reset_link.split("token=")[1]

    # 4. Verify token
    verify_resp = verify_reset_token(token, store=account_store)
    assert verify_resp["valid"] is True
    assert verify_resp["username"] == "maya.nair"
    assert verify_resp["email"] == "maya.nair@company.com"

    # 5. Reset password using the token
    reset_resp = reset_password_with_token(
        ResetPasswordWithTokenRequest(token=token, new_password="BrandNewPassword999!"),
        store=account_store,
    )
    assert reset_resp["status"] == "ok"

    # 6. Verify old password fails and new password succeeds
    assert account_store.authenticate("maya.nair", "InitialPassword2026!", Role.PROJECT_ENGINEER.value) is None
    assert account_store.authenticate("maya.nair", "BrandNewPassword999!", Role.PROJECT_ENGINEER.value) is not None

    # 7. Token is single-use: reusing the token must fail
    with pytest.raises(HTTPException) as exc_reused:
        verify_reset_token(token, store=account_store)
    assert exc_reused.value.status_code == 400


def test_expired_reset_token_rejected(account_store: LocalAccountStore) -> None:
    account = account_store.create_account(
        tenant_id="enterprise-tenant",
        username="rahul.patel",
        password="Password12345!",
        role=Role.SUPERVISOR.value,
        display_name="Rahul Patel",
        email="rahul.patel@company.com",
    )

    # Generate token with negative expiry to simulate expiration
    token = account_store.create_password_reset_token(account["id"], "enterprise-tenant", expires_minutes=-5)

    with pytest.raises(HTTPException) as exc_expired:
        verify_reset_token(token, store=account_store)
    assert exc_expired.value.status_code == 400
    assert "expired" in str(exc_expired.value.detail).lower()
