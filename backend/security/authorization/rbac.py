from __future__ import annotations

from enum import Enum


class Role(str, Enum):
    CEO = "CEO"
    FINANCE = "Finance"
    HR = "HR"
    MANAGER = "Manager"
    EMPLOYEE = "Employee"
    IT_ADMIN = "IT Admin"


# RBAC grants coarse-grained capabilities. Resource/department constraints
# are enforced separately by ABAC and policy evaluation.
ROLE_PERMISSIONS: dict[Role, frozenset[str]] = {
    Role.CEO: frozenset({
        "FILE_READ", "FILE_WRITE",
        "EMAIL_READ", "EMAIL_SEND",
        "DATABASE_READ", "DATABASE_WRITE",
        "REPORT_CREATE", "REPORT_DOWNLOAD", "FINANCE_READ", "HR_READ", "AUDIT_READ",
        "WEB_SEARCH",
        "CONNECTION_READ", "CONNECTION_WRITE", "CONNECTION_DELETE", "CONNECTION_ADMIN",
        "CONNECTION_USE", "CONNECTION_OWN_MANAGE", "CONNECTION_ORG_VIEW", "CONNECTION_ORG_MANAGE",
        "CONNECTION_AUDIT_VIEW",
    }),
    Role.FINANCE: frozenset({
        "FILE_READ", "FILE_WRITE",
        "EMAIL_READ", "EMAIL_SEND",
        "DATABASE_READ", "DATABASE_WRITE",
        "REPORT_CREATE", "REPORT_DOWNLOAD", "FINANCE_READ",
        "WEB_SEARCH",
        "CONNECTION_READ", "CONNECTION_WRITE", "CONNECTION_DELETE",
        "CONNECTION_USE", "CONNECTION_OWN_MANAGE", "CONNECTION_ORG_VIEW",
    }),
    Role.HR: frozenset({
        "FILE_READ", "FILE_WRITE",
        "EMAIL_READ", "EMAIL_SEND",
        "DATABASE_READ",
        "REPORT_CREATE", "REPORT_DOWNLOAD", "HR_READ",
        "WEB_SEARCH",
        "CONNECTION_READ", "CONNECTION_WRITE", "CONNECTION_DELETE",
        "CONNECTION_USE", "CONNECTION_OWN_MANAGE", "CONNECTION_ORG_VIEW",
    }),
    Role.MANAGER: frozenset({
        "FILE_READ", "FILE_WRITE",
        "EMAIL_READ", "EMAIL_SEND",
        "DATABASE_READ",
        "REPORT_CREATE", "REPORT_DOWNLOAD",
        "WEB_SEARCH",
        "CONNECTION_READ", "CONNECTION_WRITE", "CONNECTION_DELETE",
        "CONNECTION_USE", "CONNECTION_OWN_MANAGE", "CONNECTION_ORG_VIEW",
    }),
    Role.EMPLOYEE: frozenset({
        "FILE_READ",
        "EMAIL_READ",
        "DATABASE_READ",
        "REPORT_CREATE", "REPORT_DOWNLOAD",
        "WEB_SEARCH",
        "CONNECTION_READ", "CONNECTION_WRITE", "CONNECTION_DELETE",
        "CONNECTION_USE", "CONNECTION_OWN_MANAGE", "CONNECTION_ORG_VIEW",
    }),

    Role.IT_ADMIN: frozenset({
        "FILE_READ", "FILE_WRITE",
        "EMAIL_READ", "EMAIL_SEND",
        "DATABASE_READ", "DATABASE_WRITE",
        "AUDIT_READ", "REPORT_DOWNLOAD",
        "WEB_SEARCH",
        "CONNECTION_READ", "CONNECTION_WRITE", "CONNECTION_DELETE", "CONNECTION_ADMIN",
        "CONNECTION_USE", "CONNECTION_OWN_MANAGE", "CONNECTION_ORG_VIEW", "CONNECTION_ORG_MANAGE",
        "CONNECTION_AUDIT_VIEW",
    }),
}


def has_permission(role: Role, permission: str) -> bool:
    return permission in ROLE_PERMISSIONS.get(role, frozenset())
