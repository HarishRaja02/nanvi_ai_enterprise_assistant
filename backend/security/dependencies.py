from __future__ import annotations

import logging

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from backend.observability.logging import log_event
from backend.security.authentication_service import AuthenticationService
from backend.security.providers import OIDCIdentityProvider
from backend.security.token_validator import TokenValidator

_bearer = HTTPBearer(auto_error=False)
logger = logging.getLogger(__name__)


def get_authentication_service() -> AuthenticationService:
    provider = OIDCIdentityProvider(authorization_endpoint="/oauth2/authorize")
    return AuthenticationService(TokenValidator(), provider)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    service: AuthenticationService = Depends(get_authentication_service),
):
    if credentials is None or credentials.scheme.lower() != "bearer":
        log_event(logger, "authentication_failed", logging.WARNING, reason="missing_or_invalid_bearer_scheme")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"})
    try:
        user = service.authenticate_access_token(credentials.credentials)
        log_event(logger, "authentication_succeeded", actor_id=user.subject, tenant_id=user.tenant_id,
                  issuer=user.issuer)
        return user
    except Exception as exc:
        # Deliberately do not log the token or exception text: validators/providers may
        # include token fragments or infrastructure details in exception messages.
        log_event(logger, "authentication_failed", logging.WARNING, reason=type(exc).__name__)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired access token", headers={"WWW-Authenticate": "Bearer"})
