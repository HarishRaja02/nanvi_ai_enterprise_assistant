"""FastAPI dependencies and middleware for centralized UECP authorization enforcement."""
from __future__ import annotations

import logging
from typing import Callable
from fastapi import Depends, HTTPException, Request, status

from backend.security.dependencies import get_current_user
from backend.security.models import UserIdentity
from backend.uecp.authorization import UECPAuthorizationService, get_uecp_service
from backend.uecp.models import UECPAccessState

logger = logging.getLogger(__name__)


def require_uecp_access(permission: str | None = None) -> Callable[..., UECPAccessState]:
    """Reusable FastAPI dependency to enforce UECP platform-level authorization.

    Usage:
        @router.post("/chat")
        def chat_endpoint(
            body: ChatBody,
            user: UserAttributes = Depends(current_attributes),
            uecp_access: UECPAccessState = Depends(require_uecp_access(permission="ai.chat")),
        ):
            ...
    """

    def _uecp_dependency(
        request: Request,
        user: UserIdentity = Depends(get_current_user),
        service: UECPAuthorizationService = Depends(get_uecp_service),
    ) -> UECPAccessState:
        # Organization mapping derived strictly from authenticated server-side user context
        organization_id = user.tenant_id

        # Correlation ID from request headers if present
        cid = (
            request.headers.get("X-Request-ID")
            or request.headers.get("X-Correlation-ID")
            or getattr(request.state, "request_id", None)
        )

        decision = service.check_access(
            organization_id=organization_id,
            permission=permission,
            user_id=user.subject,
            correlation_id=cid,
        )

        if not decision.allowed:
            # Differentiate outage (503) from deliberate denial (403)
            if decision.reason in {"service_unavailable", "uecp_disabled_in_production"}:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail={
                        "error": "service_unavailable",
                        "message": "Access authorization is temporarily unavailable.",
                    },
                    headers={"Retry-After": "30"},
                )

            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "error": "access_denied",
                    "message": "Access unavailable: Your organization's Nanvi access is currently unavailable. Please contact your administrator.",
                },
            )

        return decision

    return _uecp_dependency
