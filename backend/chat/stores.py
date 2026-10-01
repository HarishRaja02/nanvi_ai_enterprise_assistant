"""Conversation stores for chat history persistence."""
from __future__ import annotations

import re
from abc import ABC, abstractmethod

from backend.chat.models import ChatMessage, ConversationSummary


def generate_conversation_title(query: str) -> str:
    """Generate a clean, meaningful conversation title from the initial prompt."""
    clean = query.strip().rstrip("?.!")
    pattern = r"^(can you please |can you |could you |please |tell me |show me |what is |what are |search the web for |search online for |search for |find |check my |lookup |look up )"
    stripped = re.sub(pattern, "", clean, flags=re.IGNORECASE).strip()
    if stripped:
        clean = stripped
    words = clean.split()
    title_words = []
    lower_words = {"in", "on", "at", "for", "to", "of", "and", "or", "the", "a", "an", "with"}
    for idx, w in enumerate(words):
        if idx > 0 and w.lower() in lower_words:
            title_words.append(w.lower())
        else:
            title_words.append(w[:1].upper() + w[1:])
    result = " ".join(title_words)
    if len(result) > 42:
        result = result[:39].rsplit(" ", 1)[0] + "…"
    return result or "New Conversation"


class ConversationStore(ABC):
    @abstractmethod
    def append(self, conversation_id: str, message: ChatMessage) -> None: ...

    @abstractmethod
    def get(self, conversation_id: str) -> tuple[ChatMessage, ...]: ...

    @abstractmethod
    def list_for_user(self, user_id: str, tenant_id: str) -> tuple[ConversationSummary, ...]: ...

    @abstractmethod
    def bind_owner(self, conversation_id: str, user_id: str, tenant_id: str) -> None: ...

    @abstractmethod
    def owner(self, conversation_id: str) -> tuple[str, str] | None: ...

    def set_active_document(self, conversation_id: str, document_id: str) -> None:
        pass

    def get_active_document(self, conversation_id: str) -> str | None:
        return None

    def set_context(self, conversation_id: str, context: object) -> None:
        pass

    def get_context(self, conversation_id: str) -> object | None:
        return None


class InMemoryConversationStore(ConversationStore):
    """Development/test conversation store. Rejected in production."""

    def __init__(self) -> None:
        import backend.core.config as cfg
        from backend.core.exceptions import ConfigurationError

        if cfg.settings.is_production:
            raise ConfigurationError(
                "InMemoryConversationStore is forbidden in production. Configure a durable PostgreSQL store."
            )
        self._messages: dict[str, list[ChatMessage]] = {}
        self._owners: dict[str, tuple[str, str]] = {}
        self._titles: dict[str, str] = {}
        self._active_docs: dict[str, str] = {}
        self._contexts: dict[str, object] = {}

    def set_active_document(self, conversation_id: str, document_id: str) -> None:
        self._active_docs[conversation_id] = document_id

    def get_active_document(self, conversation_id: str) -> str | None:
        return self._active_docs.get(conversation_id)

    def set_context(self, conversation_id: str, context: object) -> None:
        self._contexts[conversation_id] = context

    def get_context(self, conversation_id: str) -> object | None:
        return self._contexts.get(conversation_id)

    def bind_owner(self, conversation_id: str, user_id: str, tenant_id: str) -> None:
        existing = self._owners.get(conversation_id)
        if existing and existing != (user_id, tenant_id):
            raise PermissionError("Conversation does not belong to the authenticated principal")
        self._owners[conversation_id] = (user_id, tenant_id)
        self._messages.setdefault(conversation_id, [])

    def owner(self, conversation_id: str) -> tuple[str, str] | None:
        return self._owners.get(conversation_id)

    def append(self, conversation_id: str, message: ChatMessage) -> None:
        if conversation_id not in self._owners:
            raise PermissionError("Conversation is not bound to an authenticated principal")
        self._messages.setdefault(conversation_id, []).append(message)
        if conversation_id not in self._titles and message.role == "user" and message.content:
            self._titles[conversation_id] = generate_conversation_title(message.content)

    def get(self, conversation_id: str) -> tuple[ChatMessage, ...]:
        return tuple(self._messages.get(conversation_id, ()))

    def list_for_user(self, user_id: str, tenant_id: str) -> tuple[ConversationSummary, ...]:
        items = []
        for cid, (owner, owner_tenant) in self._owners.items():
            if owner != user_id or owner_tenant != tenant_id:
                continue
            messages = self._messages.get(cid, [])
            if messages:
                title = self._titles.get(cid)
                if not title:
                    user_msgs = [m for m in messages if m.role == "user"]
                    if user_msgs:
                        title = generate_conversation_title(user_msgs[0].content)
                        self._titles[cid] = title
                    else:
                        title = "New Conversation"
                items.append(ConversationSummary(cid, len(messages), messages[-1].created_at, title=title))
        return tuple(sorted(items, key=lambda x: x.last_message_at, reverse=True))
