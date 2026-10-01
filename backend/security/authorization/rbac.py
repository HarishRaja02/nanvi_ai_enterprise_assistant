from __future__ import annotations

from enum import Enum


class Role(str, Enum):
    SUPERIOR = "Superior"
    SUPERVISOR = "Supervisor"
    PROJECT_ENGINEER = "Project Engineer"
    CEO = "CEO"
    FINANCE = "Finance"
    HR = "HR"
    MANAGER = "Manager"
    EMPLOYEE = "Employee"
    IT_ADMIN = "IT Admin"


LEGACY_ROLE_ALIASES: dict[str, Role] = {
    Role.CEO.value: Role.SUPERIOR,
    Role.FINANCE.value: Role.SUPERVISOR,
    Role.MANAGER.value: Role.SUPERVISOR,
    Role.HR.value: Role.PROJECT_ENGINEER,
    Role.IT_ADMIN.value: Role.SUPERVISOR,
}


def normalize_role(value: str) -> Role | None:
    try:
        return Role(value)
    except ValueError:
        return LEGACY_ROLE_ALIASES.get(value)


# RBAC grants coarse-grained capabilities. Resource/department constraints
# are enforced separately by ABAC and policy evaluation.
ROLE_PERMISSIONS: dict[Role, frozenset[str]] = {
    Role.SUPERIOR: frozenset({
        "FILE_READ", "FILE_WRITE", "EMAIL_READ", "EMAIL_SEND",
        "DATABASE_READ", "DATABASE_WRITE", "REPORT_CREATE", "REPORT_DOWNLOAD",
        "FINANCE_READ", "HR_READ", "AUDIT_READ", "WEB_SEARCH", "USER_MANAGE",
        "CONNECTION_READ", "CONNECTION_WRITE", "CONNECTION_DELETE", "CONNECTION_ADMIN",
        "CONNECTION_USE", "CONNECTION_OWN_MANAGE", "CONNECTION_ORG_VIEW", "CONNECTION_ORG_MANAGE",
        "CONNECTION_AUDIT_VIEW",
    }),
    Role.SUPERVISOR: frozenset({
        "FILE_READ", "FILE_WRITE", "EMAIL_READ", "EMAIL_SEND",
        "DATABASE_READ", "DATABASE_WRITE", "REPORT_CREATE", "REPORT_DOWNLOAD",
        "FINANCE_READ", "HR_READ", "WEB_SEARCH", "USER_MANAGE",
        "CONNECTION_READ", "CONNECTION_WRITE", "CONNECTION_DELETE", "CONNECTION_USE",
        "CONNECTION_OWN_MANAGE", "CONNECTION_ORG_VIEW", "CONNECTION_ORG_MANAGE",
    }),
    Role.PROJECT_ENGINEER: frozenset({"FILE_READ"}),
    Role.CEO: frozenset({
        "FILE_READ", "FILE_WRITE",
        "EMAIL_READ", "EMAIL_SEND",
        "DATABASE_READ", "DATABASE_WRITE",
        "REPORT_CREATE", "REPORT_DOWNLOAD", "FINANCE_READ", "HR_READ", "AUDIT_READ",
        "WEB_SEARCH", "USER_MANAGE",
        "CONNECTION_READ", "CONNECTION_WRITE", "CONNECTION_DELETE", "CONNECTION_ADMIN",
        "CONNECTION_USE", "CONNECTION_OWN_MANAGE", "CONNECTION_ORG_VIEW", "CONNECTION_ORG_MANAGE",
        "CONNECTION_AUDIT_VIEW",
    }),
    Role.FINANCE: frozenset({
        "FILE_READ", "FILE_WRITE",
        "EMAIL_READ", "EMAIL_SEND",
        "DATABASE_READ", "DATABASE_WRITE",
        "REPORT_CREATE", "REPORT_DOWNLOAD", "FINANCE_READ",
        "WEB_SEARCH", "USER_MANAGE",
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
