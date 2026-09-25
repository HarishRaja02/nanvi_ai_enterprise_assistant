from __future__ import annotations
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from backend.security.authorization import UserAttributes
from backend.sources.models import SourceReference


class Capability(StrEnum):
    KNOWLEDGE = "knowledge"
    DATABASE = "database"
    EMAIL = "email"
    GOOGLE_DRIVE = "google_drive"
    DATA_ANALYSIS = "data_analysis"
    REPORT = "report"
    WEB_SEARCH = "web_search"
    GITHUB = "github"


@dataclass(frozen=True)
class AgentRequest:
    request_id: str
    user: UserAttributes
    query: str
    history: tuple[Any, ...] = ()


@dataclass(frozen=True)
class AgentResponse:
    capability: Capability
    content: Any
    sources: tuple[SourceReference, ...] = ()
    report_id: str | None = None
    deterministic: bool = False



@dataclass
class OrchestrationState:
    """LangGraph state. Deliberately contains no passwords, API keys, OAuth tokens, or DB credentials."""
    request_id: str
    user_id: str
    tenant_id: str
    query: str
    roles: tuple[str, ...] = ()
    department: str | None = None
    capability: Capability | None = None
    response: AgentResponse | None = None
    error: str | None = None
    trace: list[str] = field(default_factory=list)
    history: tuple[Any, ...] = ()

    @classmethod
    def from_request(cls, request: AgentRequest) -> "OrchestrationState":
        return cls(
            request_id=request.request_id,
            user_id=request.user.user_id,
            tenant_id=request.user.tenant_id,
            query=request.query,
            roles=tuple(sorted(request.user.roles)),
            department=request.user.department,
            history=getattr(request, "history", ()),
        )
