from __future__ import annotations
from dataclasses import dataclass, field
from typing import Iterable

from backend.security.authorization import Permission


@dataclass(frozen=True)
class ToolPolicy:
    name: str
    permissions: frozenset[Permission]
    enabled: bool = True

    @classmethod
    def single(cls, name: str, permission: Permission, enabled: bool = True) -> "ToolPolicy":
        return cls(name, frozenset({permission}), enabled)


class ToolAllowlist:
    """Explicit backend tool allowlist. LLM output can only select known tool names."""
    DEFAULT_POLICIES = (
        ToolPolicy.single("knowledge", Permission.FILE_READ),
        ToolPolicy.single("database", Permission.DATABASE_READ),
        ToolPolicy.single("email", Permission.EMAIL_READ),
        ToolPolicy("data_analysis", frozenset({Permission.DATABASE_READ, Permission.FILE_READ}), True),
        ToolPolicy.single("report", Permission.REPORT_CREATE),
        ToolPolicy.single("web_search", Permission.WEB_SEARCH),
    )

    def __init__(self, policies: Iterable[ToolPolicy] | None = None) -> None:
        selected = tuple(policies or self.DEFAULT_POLICIES)
        self._policies = {p.name: p for p in selected}

    def get(self, tool_name: str) -> ToolPolicy | None:
        return self._policies.get(tool_name)

    def is_allowed(self, tool_name: str) -> bool:
        policy = self.get(tool_name)
        return bool(policy and policy.enabled)

    def permission_allowed(self, tool_name: str, permission: Permission) -> bool:
        policy = self.get(tool_name)
        return bool(policy and policy.enabled and permission in policy.permissions)
