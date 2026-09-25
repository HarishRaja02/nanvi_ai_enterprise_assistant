from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from backend.agents.models import AgentResponse

@dataclass(frozen=True)
class ChatRequest:
    query: str
    conversation_id: str | None = None
    rag_enabled: bool = True

@dataclass(frozen=True)
class ChatMessage:
    role: str
    content: str
    created_at: datetime

@dataclass(frozen=True)
class ConversationSummary:
    conversation_id: str
    message_count: int
    last_message_at: datetime
    title: str = "New Conversation"

@dataclass(frozen=True)
class ChatResponse:
    conversation_id: str
    answer: str
    sources: tuple[Any, ...]
    capability: str
    trace: tuple[str, ...]
    history: tuple[ChatMessage, ...]
    report_id: str | None = None

