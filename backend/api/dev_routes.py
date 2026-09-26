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
    username: str = Field(default="manager", min_length=1, max_length=50)
    password: str = Field(default="", max_length=200)


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
    # Keep the original development behavior.
    if settings.app_env == "development":
        if not settings.jwt_secret:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Development authentication requires JWT_SECRET.",
            )
        return

    # Production demo deployments must explicitly opt in.
    demo_enabled = getattr(settings, "demo_auth_enabled", False)

    if not demo_enabled:
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
    """Generate a JWT for one of the explicitly configured demo accounts."""

    _check_demo_mode()

    body = body or DevTokenRequest()
    username = body.username.strip().lower()

    account = DEMO_ACCOUNTS.get(username)

    if account is None or body.password != account["password"]:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid demo credentials",
        )

    now = int(time.time())

    payload = {
        "sub": f"demo-{username}",
        "iss": "nanvi-dev",
        "aud": "nanvi-dev",
        "iat": now,
        "exp": now + 86400,
        "name": account["name"],
        "email": account["email"],
        "tenant_id": "enterprise-tenant",
        "department": account["department"],
        "roles": [account["role"]],
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