from __future__ import annotations

import logging

from backend.observability.logging import log_event
from backend.security.authorization.abac import Resource, UserAttributes
from backend.security.authorization.permissions import Permission
from backend.security.authorization.policies import AuthorizationDecision, PermissionPolicy

logger = logging.getLogger(__name__)


class AuthorizationService:
    def __init__(self, policy: PermissionPolicy | None = None) -> None:
        self._policy = policy or PermissionPolicy()

    def authorize(
        self,
        user: UserAttributes,
        action: Permission | str,
        resource: Resource,
    ) -> AuthorizationDecision:
        permission = action if isinstance(action, Permission) else Permission(action)
        decision = self._policy.evaluate(user, permission, resource)
        if decision.allowed:
            log_event(logger, "authorization_allowed", actor_id=user.user_id, tenant_id=user.tenant_id,
                      permission=permission.value, resource_id=resource.resource_id, resource_type=resource.resource_type)
        else:
            log_event(logger, "authorization_denied", logging.WARNING, actor_id=user.user_id,
                      tenant_id=user.tenant_id, permission=permission.value, resource_id=resource.resource_id,
                      resource_type=resource.resource_type, reason=decision.reason)
        return decision
