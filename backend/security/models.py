from __future__ import annotations
from dataclasses import dataclass, field
from backend.security.authorization.rbac import Role


@dataclass(frozen=True)
class UserIdentity:
    subject: str
    issuer: str
    email: str | None = None
    name: str | None = None
    tenant_id: str | None = None
    department: str | None = None
    roles: frozenset[Role] = field(default_factory=frozenset)
