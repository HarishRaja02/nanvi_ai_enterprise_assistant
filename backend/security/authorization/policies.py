from __future__ import annotations

from dataclasses import dataclass

from backend.security.authorization.abac import Resource, UserAttributes, department_allows, resource_allows, same_tenant
from backend.security.authorization.permissions import Permission
from backend.security.authorization.rbac import Role, has_permission


@dataclass(frozen=True)
class AuthorizationDecision:
    allowed: bool
    reason: str


class PermissionPolicy:
    """Central policy evaluation. No AI/LLM input is used."""

    def evaluate(
        self,
        user: UserAttributes,
        permission: Permission,
        resource: Resource,
    ) -> AuthorizationDecision:
        if not same_tenant(user, resource):
            return AuthorizationDecision(False, "Tenant boundary violation")

        if not user.roles:
            return AuthorizationDecision(False, "User has no assigned role")

        if not any(has_permission(role, permission.value) for role in user.roles):
            return AuthorizationDecision(False, "Role does not grant permission")

        if not department_allows(user, resource, permission.value):
            return AuthorizationDecision(False, "Department policy denied access")

        if not resource_allows(user, resource, permission.value):
            return AuthorizationDecision(False, "Resource policy denied access")

        return AuthorizationDecision(True, "Authorization policy allowed access")


class AuthorizationPolicySet(PermissionPolicy):
    """Named extension point for future policy composition."""
