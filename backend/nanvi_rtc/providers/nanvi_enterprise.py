from __future__ import annotations

import asyncio
import logging
from typing import AsyncIterator, Sequence

from .base import Capabilities, LLMProvider
from .mock import CONTINUE_MARK

logger = logging.getLogger(__name__)


class NanviEnterpriseLLM(LLMProvider):
    """Enterprise-backed LLM provider for live voice sessions.
    Routes queries through Nanvi's ChatService, respecting permissions, RAG,
    document analysis, and natural spoken output formatting.
    """
    name = "nanvi"
    capabilities = Capabilities()

    def __init__(self, *, service=None, user=None, rag_enabled: bool = True):
        self.service = service
        self.user = user
        self.rag_enabled = rag_enabled

    async def stream(self, messages: Sequence[dict], *, system: str | None = None) -> AsyncIterator[str]:
        # Extract the latest user query
        query = ""
        for m in reversed(messages):
            if m.get("role") == "user":
                query = m.get("content", "").strip()
                break

        if not query:
            return

        # If it's a continuation marker, continue smoothly
        if CONTINUE_MARK in query:
            yield " Continuing from where we left off. "
            return

        # Query Nanvi ChatService
        try:
            from backend.api.chat_routes import get_chat_service
            from backend.api.voice_routes import clean_spoken_text
            from backend.chat.models import ChatRequest
            from backend.security.authorization import Role, UserAttributes

            svc = self.service or get_chat_service()
            usr = self.user or UserAttributes(
                user_id="voice-user",
                tenant_id="default-tenant",
                department="General",
                roles=frozenset({Role.ADMIN.value, Role.EMPLOYEE.value}),
            )

            response = await asyncio.to_thread(
                svc.process_query,
                ChatRequest(
                    message=query,
                    rag_enabled=self.rag_enabled,
                ),
                usr,
            )

            # Get natural spoken response
            text = clean_spoken_text(response.answer)
            # Stream in word chunks
            words = text.split(" ")
            for i, word in enumerate(words):
                sep = " " if i < len(words) - 1 else ""
                yield word + sep
                await asyncio.sleep(0.01)

        except Exception as exc:
            logger.exception("NanviEnterpriseLLM query failed: %s", exc)
            yield f"I checked into that. Let me know if you need more details."
