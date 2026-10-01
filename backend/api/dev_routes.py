# """Development-only authentication endpoints.

# These endpoints are ONLY available when ``APP_ENV=development`` and ``JWT_SECRET``
# is configured.  They generate locally-signed JWTs for developer testing so the
# full authentication/authorization flow can be exercised without a real OIDC
# provider.

# NEVER available in production.
# NEVER expose JWT_SECRET to the frontend.
# """
# from __future__ import annotations

# import time

# import jwt
# from fastapi import APIRouter, HTTPException, status
# from pydantic import BaseModel, Field

# from backend.core.config import settings

# router = APIRouter(prefix="/dev", tags=["development"])


# class DevTokenRequest(BaseModel):
#     role: str = Field(default="Manager", min_length=1, max_length=50)
#     department: str = Field(default="Engineering", min_length=1, max_length=100)
#     name: str = Field(default="Dev User", min_length=1, max_length=200)
#     email: str = Field(default="dev@nanvi.local", min_length=1, max_length=200)


# def _check_dev_mode() -> None:
#     if settings.app_env != "development":
#         raise HTTPException(
#             status_code=status.HTTP_404_NOT_FOUND,
#             detail="Not found",
#         )
#     if not settings.jwt_secret:
#         raise HTTPException(
#             status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
#             detail="Development authentication requires JWT_SECRET to be configured.",
#         )


# @router.post("/token")
# def create_dev_token(body: DevTokenRequest | None = None):
#     """Generate a locally-signed JWT for development testing.

#     This token is accepted by the backend's dev-mode token validator and
#     exercises the real authentication/authorization flow.
#     """
#     _check_dev_mode()
#     body = body or DevTokenRequest()

#     now = int(time.time())
#     payload = {
#         "sub": "dev-user-001",
#         "iss": "nanvi-dev",
#         "aud": "nanvi-dev",
#         "iat": now,
#         "exp": now + 86400,  # 24 hours
#         "name": body.name,
#         "email": body.email,
#         "tenant_id": "enterprise-tenant",
#         "department": body.department,
#         "roles": [body.role],
#     }
#     token = jwt.encode(payload, settings.jwt_secret, algorithm="HS256")
#     return {"access_token": token, "token_type": "bearer", "expires_in": 86400}
"""Explicitly enabled demo authentication endpoints.

These endpoints are intended only for controlled demo deployments.
They must never be enabled on a normal production enterprise deployment.
"""

from __future__ import annotations

import time

import jwt
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from backend.core.config import settings

router = APIRouter(prefix="/dev", tags=["development"])


class DevTokenRequest(BaseModel):
    username: str | None = Field(default=None, max_length=50)
    password: str = Field(default="", max_length=200)
    role: str | None = Field(default=None, max_length=50)
    department: str | None = Field(default=None, max_length=100)
    name: str | None = Field(default=None, max_length=200)
    email: str | None = Field(default=None, max_length=200)


DEMO_ACCOUNTS = {
    "ceo": {
        "password": "ceo@nanvi",
        "role": "CEO",
        "department": "Executive",
        "name": "Arjun Mehta",
        "email": "ceo@nanvi.local",
    },
    "finance": {
        "password": "finance@nanvi",
        "role": "Finance",
        "department": "Finance",
        "name": "Priya Sharma",
        "email": "finance@nanvi.local",
    },
    "hr": {
        "password": "hr@nanvi",
        "role": "HR",
        "department": "Human Resources",
        "name": "Kavita Reddy",
        "email": "hr@nanvi.local",
    },
    "manager": {
        "password": "manager@nanvi",
        "role": "Manager",
        "department": "Engineering",
        "name": "Rahul Patel",
        "email": "manager@nanvi.local",
    },
    "employee": {
        "password": "employee@nanvi",
        "role": "Employee",
        "department": "Operations",
        "name": "Ankit Singh",
        "email": "employee@nanvi.local",
    },
    "itadmin": {
        "password": "itadmin@nanvi",
        "role": "IT Admin",
        "department": "IT",
        "name": "Deepak Kumar",
        "email": "itadmin@nanvi.local",
    },
}


def _check_demo_mode() -> None:
    if settings.is_production or not settings.allows_synthetic_data:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="DEPENDENCY_UNAVAILABLE: Demo authentication is forbidden in production.",
        )

    # Keep the original development behavior.
    if settings.is_development:
        if not settings.jwt_secret:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Development authentication requires JWT_SECRET.",
            )
        return

    # Production demo deployments must explicitly opt in.
    demo_enabled = getattr(settings, "demo_auth_enabled", False)

    if not demo_enabled and not settings.is_demo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Not found",
        )

    if not settings.jwt_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Demo authentication requires JWT_SECRET.",
        )


@router.post("/token")
def create_dev_token(body: DevTokenRequest | None = None):
    """Generate a JWT for one of the demo accounts or dev test requests."""

    _check_demo_mode()

    body = body or DevTokenRequest()
    raw_username = (body.username or "").strip().lower()
    raw_role = (body.role or "").strip().lower().replace(" ", "")

    target_key = raw_username or raw_role
    account = DEMO_ACCOUNTS.get(target_key) if target_key else None

    # In dev mode, if role or name is provided directly, allow standard dev token issuance
    if account is None and settings.app_env == "development":
        account = {
            "name": body.name or "Dev User",
            "email": body.email or "dev@nanvi.local",
            "department": body.department or "Engineering",
            "role": body.role or "Manager",
            "password": "",
        }

    # Verify password if specified or if required
    if account is not None and account.get("password") and body.password:
        if body.password != account["password"]:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid demo credentials",
            )
    elif account is not None and account.get("password") and not body.password:
        # In development environment, allow passwordless login for automated tests/dev
        if settings.app_env != "development":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid demo credentials",
            )

    if account is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid demo credentials",
        )

    now = int(time.time())
    sub = f"demo-{target_key}" if target_key else "dev-user-001"

    payload = {
        "sub": sub,
        "iss": "nanvi-dev",
        "aud": "nanvi-dev",
        "iat": now,
        "exp": now + 86400,
        "name": body.name or account["name"],
        "email": body.email or account["email"],
        "tenant_id": "enterprise-tenant",
        "department": body.department or account["department"],
        "roles": [body.role or account["role"]],
    }

    token = jwt.encode(
        payload,
        settings.jwt_secret,
        algorithm="HS256",
    )

    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in": 86400,
    }