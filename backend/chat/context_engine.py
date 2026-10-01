"""Centralized Conversation & Task Context Engine for Nanvi AI Enterprise Assistant.

Maintains a single source of truth for conversational and operational context
shared across text, voice, UI, agents, and predictive actions.
Strictly adheres to Section 6.1 of docs/NANVI_SPEC.md.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4
from pydantic import BaseModel, Field

from backend.security.authorization import UserAttributes

logger = logging.getLogger(__name__)


class UserContext(BaseModel):
    id: str
    role: str = ""
    department: str | None = None
    tenant_id: str = ""
    permissions: list[str] = Field(default_factory=list)


class PageContext(BaseModel):
    route: str = "/chat"
    page_type: str = "chat"
    title: str = "Enterprise Assistant"


class EntityContext(BaseModel):
    type: str = ""  # e.g., "invoice", "employee", "customer", "contract"
    id: str = ""
    name: str = ""
    data: dict[str, Any] = Field(default_factory=dict)


class DocumentContext(BaseModel):
    document_id: str = ""
    filename: str = ""
    page: int | None = None

# Code-switching and Indian language conversational markers (Hinglish and Tamil)
HINGLISH_MARKERS = {
    "kya", "kitna", "kitni", "kitne", "hai", "hain", "dikhao", "batao",
    "karo", "theek", "haan", "nahin", "nahi", "dekhna", "bhejo", "kaise",
    "chahiye", "kab", "kisko", "wala", "wali", "wale", "kahan", "pehle",
    "baad", "aur", "ya", "lekin", "bhi", "toh", "ab", "kuch", "mujhe",
}

TAMIL_MARKERS = {
    "enna", "eppadi", "kaattu", "sollinga", "evvalavu", "enga", "irukku",
    "illai", "aamaa", "pannunga", "anuppunga", "theriyuma",
}


def detect_code_switching(text: str) -> str:
    """Detect whether user query uses code-switching (Hinglish, Tamil-English) or standard English."""
    if not text:
        return "en-IN"
    tokens = set(re.findall(r"\b[a-zA-Z]+\b", text.lower()))
    if tokens.intersection(HINGLISH_MARKERS):
        return "hinglish"
    if tokens.intersection(TAMIL_MARKERS):
        return "ta-IN"
    return "en-IN"


def detect_verbosity_command(query: str) -> str | None:
    """Detect if a user voice query is explicitly requesting an adjustment to response verbosity."""
    if not query:
        return None
    q = query.strip().lower()

    concise_patterns = [
        r"\b(?:be|keep it|make it)?\s*(?:more\s+)?(?:brief|concise|short|shorter)\b",
        r"\bshorter please\b",
        r"\btoo long\b",
        r"\bjust (?:the )?(?:highlights|summary|bullets)\b",
        r"\bconcise mode\b",
    ]
    for pat in concise_patterns:
        if re.search(pat, q):
            return "concise"

    detailed_patterns = [
        r"\b(?:tell me more|give me more details?|explain further|elaborate|expand on that)\b",
        r"\b(?:be|make it)?\s*(?:more\s+)?detailed\b",
        r"\bgive full details\b",
        r"\bdetailed mode\b",
    ]
    for pat in detailed_patterns:
        if re.search(pat, q):
            return "detailed"

    normal_patterns = [
        r"\b(?:normal|standard|balanced|default)\s*(?:mode|verbosity)?\b",
        r"\breset verbosity\b",
    ]
    for pat in normal_patterns:
        if re.search(pat, q):
            return "normal"

    return None


class UserPreferences(BaseModel):
    verbosity: str = "normal"  # "concise" | "normal" | "detailed"
    privacy_mode: bool = False
    language: str = "auto"     # "auto" | "en-IN" | "hinglish" | "ta-IN" | "en-US"


class ConversationState(BaseModel):
    turn_state: str = "idle"  # "idle" | "listening" | "thinking" | "speaking" | "interrupted"


class ConversationContext(BaseModel):
    """Centralized context object conforming to Section 6.1 of docs/NANVI_SPEC.md."""
    session_id: str = Field(default_factory=lambda: uuid4().hex)
    conversation_id: str
    user: UserContext
    active_page: PageContext = Field(default_factory=PageContext)
    active_entity: EntityContext | None = None
    active_document: DocumentContext | None = None
    last_intent: str | None = None
    last_result_ref: str | None = None
    last_ui: dict[str, Any] | None = None
    last_sources: list[dict[str, Any]] = Field(default_factory=list)
    ui_entity_index: dict[str, Any] = Field(default_factory=dict)
    user_preferences: UserPreferences = Field(default_factory=UserPreferences)
    conversation_state: ConversationState = Field(default_factory=ConversationState)
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def sanitized_slice(self) -> dict[str, Any]:
        """Produce a safe, minimal slice of context for LLM prompts and tools.
        
        Never leaks sensitive credentials, API keys, or raw tenant secrets.
        """
        return {
            "active_page": self.active_page.model_dump(),
            "active_entity": self.active_entity.model_dump() if self.active_entity else None,
            "active_document": self.active_document.model_dump() if self.active_document else None,
            "last_intent": self.last_intent,
            "ui_entity_keys": list(self.ui_entity_index.keys()),
            "user_preferences": self.user_preferences.model_dump(),
        }


class ContextManager:
    """Thread-safe context manager for storing and updating conversation contexts."""

    def __init__(self) -> None:
        self._contexts: dict[str, ConversationContext] = {}

    def get(self, conversation_id: str) -> ConversationContext | None:
        return self._contexts.get(conversation_id)

    def get_or_create(
        self,
        conversation_id: str,
        user: UserAttributes,
        session_id: str | None = None,
    ) -> ConversationContext:
        ctx = self._contexts.get(conversation_id)
        if ctx is None:
            user_roles = [r.value if hasattr(r, "value") else str(r) for r in user.roles]
            user_ctx = UserContext(
                id=user.user_id,
                role=user_roles[0] if user_roles else "",
                department=user.department,
                tenant_id=user.tenant_id,
                permissions=user_roles,
            )
            ctx = ConversationContext(
                session_id=session_id or uuid4().hex,
                conversation_id=conversation_id,
                user=user_ctx,
            )
            self._contexts[conversation_id] = ctx
        return ctx

    def update(self, conversation_id: str, updates: dict[str, Any]) -> ConversationContext:
        ctx = self._contexts.get(conversation_id)
        if ctx is None:
            raise KeyError(f"Context not found for conversation {conversation_id}")

        data = ctx.model_dump()
        for k, v in updates.items():
            if k in data and v is not None:
                data[k] = v
        data["updated_at"] = datetime.now(timezone.utc).isoformat()
        updated_ctx = ConversationContext(**data)
        self._contexts[conversation_id] = updated_ctx
        return updated_ctx

    def update_from_interaction(
        self,
        conversation_id: str,
        user: UserAttributes,
        query: str,
        answer: str,
        capability: str,
        sources: list[dict[str, Any]],
        active_document_id: str | None = None,
        active_entity: dict[str, Any] | None = None,
    ) -> ConversationContext:
        """Update context automatically after a completed chat/voice interaction."""
        ctx = self.get_or_create(conversation_id, user)
        updates: dict[str, Any] = {
            "last_intent": capability,
            "last_sources": sources,
            "last_result_ref": f"turn-{int(datetime.now(timezone.utc).timestamp())}",
        }
        if active_document_id:
            updates["active_document"] = DocumentContext(
                document_id=active_document_id,
                filename=active_document_id,
            ).model_dump()
        if active_entity:
            updates["active_entity"] = active_entity

        return self.update(conversation_id, updates)

    def get_preferences(self, conversation_id: str) -> UserPreferences:
        """Retrieve user preferences for a conversation context."""
        ctx = self.get(conversation_id)
        if ctx and ctx.user_preferences:
            return ctx.user_preferences
        return UserPreferences()

    def update_preferences(self, conversation_id: str, updates: dict[str, Any]) -> UserPreferences:
        """Update and persist user preferences for a conversation context."""
        ctx = self.get(conversation_id)
        if not ctx:
            raise KeyError(f"Context not found for conversation {conversation_id}")
        current_data = ctx.user_preferences.model_dump()
        for k, v in updates.items():
            if k in current_data and v is not None:
                current_data[k] = v
        new_prefs = UserPreferences(**current_data)
        self.update(conversation_id, {"user_preferences": new_prefs.model_dump()})
        return new_prefs


# Singleton context manager instance for backend lifecycle
context_manager = ContextManager()
