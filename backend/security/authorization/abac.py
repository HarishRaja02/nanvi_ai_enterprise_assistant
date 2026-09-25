from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from backend.security.authorization.rbac import Role


@dataclass(frozen=True)
class UserAttributes:
    user_id: str
    tenant_id: str
    department: str | None
    roles: frozenset[Role] = field(default_factory=frozenset)


@dataclass(frozen=True)
class Resource:
    resource_id: str
    resource_type: str
    tenant_id: str
    owner_id: str | None = None
    department: str | None = None
    attributes: dict[str, Any] = field(default_factory=dict)


def same_tenant(user: UserAttributes, resource: Resource) -> bool:
    return bool(user.tenant_id) and user.tenant_id == resource.tenant_id


def department_allows(
    user: UserAttributes,
    resource: Resource,
    permission: str,
) -> bool:
    """Apply department boundaries for sensitive domain permissions.

    A resource with no department is not automatically restricted by department.
    Sensitive domain permissions require matching department when the resource
    carries a department attribute.
    """
    sensitive_departments = {
        "FINANCE_READ": "Finance",
        "HR_READ": "HR",
    }
    required_department = sensitive_departments.get(permission)

    if required_department is None:
        return True

    if resource.department is None:
        return user.department == required_department

    return resource.department == user.department == required_department


def resource_allows(
    user: UserAttributes,
    resource: Resource,
    permission: str,
) -> bool:
    """Enforce resource-level boundaries, including sensitive company files."""
    if resource.resource_type in {"user_file", "user_report"}:
        return resource.owner_id == user.user_id

    restricted_department = resource.attributes.get("restricted_department")
    if restricted_department:
        # Company-file restrictions are independent of the LLM. Privileged
        # enterprise roles may access restricted files; other users must belong
        # to the resource's department.
        privileged_roles = {Role.CEO, Role.IT_ADMIN}
        if user.roles.intersection(privileged_roles):
            return True
        return user.department == restricted_department

    return True
