"""Development-only authentication endpoints.

These endpoints are ONLY available when ``APP_ENV=development`` and ``JWT_SECRET``
is configured.  They generate locally-signed JWTs for developer testing so the
full authentication/authorization flow can be exercised without a real OIDC
provider.

NEVER available in production.
NEVER expose JWT_SECRET to the frontend.
"""
from __future__ import annotations

import time

import jwt
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from backend.core.config import settings

router = APIRouter(prefix="/dev", tags=["development"])


class DevTokenRequest(BaseModel):
    role: str = Field(default="Manager", min_length=1, max_length=50)
    department: str = Field(default="Engineering", min_length=1, max_length=100)
    name: str = Field(default="Dev User", min_length=1, max_length=200)
    email: str = Field(default="dev@nanvi.local", min_length=1, max_length=200)


def _check_dev_mode() -> None:
    if settings.app_env != "development":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Not found",
        )
    if not settings.jwt_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Development authentication requires JWT_SECRET to be configured.",
        )


@router.post("/token")
def create_dev_token(body: DevTokenRequest | None = None):
    """Generate a locally-signed JWT for development testing.

    This token is accepted by the backend's dev-mode token validator and
    exercises the real authentication/authorization flow.
    """
    _check_dev_mode()
    body = body or DevTokenRequest()

    now = int(time.time())
    payload = {
        "sub": "dev-user-001",
        "iss": "nanvi-dev",
        "aud": "nanvi-dev",
        "iat": now,
        "exp": now + 86400,  # 24 hours
        "name": body.name,
        "email": body.email,
        "tenant_id": "enterprise-tenant",
        "department": body.department,
        "roles": [body.role],
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm="HS256")
    return {"access_token": token, "token_type": "bearer", "expires_in": 86400}
