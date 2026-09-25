from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any, Protocol

from .models import AgentRequest, AgentResponse, Capability


class LLMProvider(Protocol):
    """Provider abstraction for an LLM. Credentials belong to the provider/backend layer, never graph state."""
    def classify(self, query: str, capabilities: tuple[Capability, ...]) -> Capability: ...
    def generate(self, prompt: str, *, system: str | None = None) -> str: ...


class Agent(ABC):
    """Clean capability-agent contract. Agents receive an already authenticated request."""
    capability: Capability

    @abstractmethod
    def run(self, request: AgentRequest) -> AgentResponse:
        raise NotImplementedError


class Router(ABC):
    @abstractmethod
    def route(self, query: str) -> Capability:
        raise NotImplementedError


class LLMRouter(Router):
    """LLM-assisted routing only; routing never grants permission."""
    def __init__(self, llm: LLMProvider):
        self._llm = llm

    def route(self, query: str) -> Capability:
        return self._llm.classify(query, tuple(Capability))


class RuleBasedRouter(Router):
    """Deterministic development/test router. It is not a security mechanism."""
    _rules = (
        (Capability.REPORT, (
            "generate report", "export report", "create report", "download report",
            "make report", "build report", "new report", "report", "summarize report",
            "in word", "in excel", "in pdf", "in doc", "in docx", "in xlsx", "in txt", "in text",
            "renewal schedule", "contract schedule", "schedule in word", "schedule in excel",
            "export to word", "export to excel", "export to pdf", "export to txt",
            "download as word", "download as pdf", "download as excel", "download as docx",
            "generate document", "create document", "put this in a doc", "put this in doc", "put this in word",
            "generate contract renewal schedule",
        )),
        (Capability.EMAIL, ("email", "mail", "asked", "inbox", "thread")),
        (Capability.DATABASE, (
            "invoice", "invoices", "employee", "employees", "database", "overdue",
            "ledger", "transaction", "transactions", "balance", "balances",
            "sql", "sql tables", "table", "tables", "records", "db", "query", "schema",
        )),
        (Capability.DATA_ANALYSIS, ("compare", "trend", "average", "total", "analysis", "month")),
        (Capability.WEB_SEARCH, (
            "web", "search the web", "search online", "browse web", "google", "internet", "online",
            "market news", "industry news", "external", "gold", "silver", "price", "prices", "rate", "rates",
            "stock", "weather", "today", "chennai", "india", "news", "crypto", "bitcoin", "ipl", "score",
            "live", "latest",
        )),
        (Capability.KNOWLEDGE, ("document", "documents", "file", "files", "project", "contract")),
    )

    def route(self, query: str) -> Capability:
        text = query.casefold()
        for capability, keywords in self._rules:
            if any(keyword in text for keyword in keywords):
                return capability
        return Capability.KNOWLEDGE
