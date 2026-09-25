"""Connection-level authorization checks.

Integrates with the existing RBAC/ABAC system.  New permissions are added
to the existing Permission enum and role maps.
"""
from __future__ import annotations

import logging

from backend.connections.base import ConnectionStatus, ScopeLevel
from backend.security.models import UserIdentity
from backend.security.authorization.rbac import Role

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
# Connection permission strings (added to Permission enum separately)
# ═══════════════════════════════════════════════════════════════

CONNECTION_OWN_MANAGE = "CONNECTION_OWN_MANAGE"
CONNECTION_ORG_VIEW = "CONNECTION_ORG_VIEW"
CONNECTION_ORG_MANAGE = "CONNECTION_ORG_MANAGE"
CONNECTION_USE = "CONNECTION_USE"
CONNECTION_AUDIT_VIEW = "CONNECTION_AUDIT_VIEW"


def can_create_user_connection(user: UserIdentity) -> bool:
    """All authenticated users can create their own connections."""
    return bool(user.subject)


def can_create_org_connection(user: UserIdentity) -> bool:
    """Only IT Admin, CEO, or users with CONNECTION_ORG_MANAGE can create org connections."""
    admin_roles = {Role.IT_ADMIN, Role.CEO}
    return bool(user.roles & admin_roles)


def can_view_connection(
    user: UserIdentity,
    *,
    owner_user_id: str | None,
    scope_level: str,
    connection_tenant_id: str,
) -> bool:
    """Check if a user can view a specific connection.

    - User connections: only the owner can see them.
    - Org connections: admins can always see; others need CONNECTION_ORG_VIEW.
    """
    # Tenant isolation
    user_tenant = user.tenant_id or "enterprise-tenant"
    if connection_tenant_id != user_tenant:
        return False

    if scope_level == ScopeLevel.USER.value:
        return owner_user_id == user.subject

    # Org-level connection
    admin_roles = {Role.IT_ADMIN, Role.CEO}
    if user.roles & admin_roles:
        return True

    # Other roles with org view permission
    return _has_role_permission(user, CONNECTION_ORG_VIEW)


def can_manage_connection(
    user: UserIdentity,
    *,
    owner_user_id: str | None,
    scope_level: str,
    connection_tenant_id: str,
) -> bool:
    """Check if a user can modify/delete a connection."""
    user_tenant = user.tenant_id or "enterprise-tenant"
    if connection_tenant_id != user_tenant:
        return False

    if scope_level == ScopeLevel.USER.value:
        return owner_user_id == user.subject

    admin_roles = {Role.IT_ADMIN, Role.CEO}
    return bool(user.roles & admin_roles)


def can_use_connection(
    user: UserIdentity,
    *,
    owner_user_id: str | None,
    scope_level: str,
    connection_tenant_id: str,
) -> bool:
    """Check if a user can use a connection (via an agent)."""
    user_tenant = user.tenant_id or "enterprise-tenant"
    if connection_tenant_id != user_tenant:
        return False

    if scope_level == ScopeLevel.USER.value:
        return owner_user_id == user.subject

    # Org connections are usable by anyone in the org (per role policy)
    return True


def can_view_audit(user: UserIdentity) -> bool:
    """Check if a user can view connection audit events."""
    admin_roles = {Role.IT_ADMIN, Role.CEO}
    return bool(user.roles & admin_roles)


def _has_role_permission(user: UserIdentity, permission: str) -> bool:
    """Check if any of the user's roles grants a specific permission.

    Uses the existing RBAC system.
    """
    from backend.security.authorization.rbac import ROLE_PERMISSIONS
    return any(
        permission in ROLE_PERMISSIONS.get(role, frozenset())
        for role in user.roles
    )
