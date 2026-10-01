"""LLM-backed ChatAnswerer that uses the provider abstraction.

This answerer takes a ``PromptContext`` (with separated trust boundaries),
renders it into a structured prompt, and sends it to the LLM provider.
The LLM explains tool results but never fabricates data.
"""
from __future__ import annotations

import logging

from backend.chat.service import ChatAnswerer
from backend.llm.provider import BaseLLMProvider, LLMProviderError
from backend.security.ai.context import PromptContext, PromptContextBuilder
from backend.observability.logging import log_event

logger = logging.getLogger(__name__)


class LLMChatAnswerer(ChatAnswerer):
    """Production answerer that sends PromptContext to an LLM provider.

    The LLM receives:
    - System policy (application-owned)
    - User query (untrusted, marked)
    - Retrieved content (untrusted, marked)
    - Tool results (untrusted, marked)

    The LLM NEVER receives:
    - API keys, database credentials, OAuth secrets
    - Raw filesystem paths
    - System prompt extraction is defended by PromptContext boundaries
    """

    def __init__(self, provider: BaseLLMProvider) -> None:
        self._provider = provider

    _GREETINGS = frozenset({
        "hi", "hello", "hey", "hola", "namaste",
        "good morning", "good afternoon", "good evening",
        "greetings", "help", "who are you", "what can you do",
        "what are you", "how are you", "hi nanvi", "hello nanvi",
    })

    _CONVERSATIONAL_KEYWORDS = frozenset({
        "what was my", "first question", "previous question", "what did i",
        "what did we", "why is it", "tell me more", "how does it", "repeat that",
        "what else", "what did you say", "summarize that", "who am i",
    })

    def answer(self, context: PromptContext) -> str:
        query_norm = context.user.value.strip().casefold().rstrip("!?.,")
        is_greeting = query_norm in self._GREETINGS
        has_history = bool(context.conversation_history)
        is_convo_query = any(k in query_norm for k in self._CONVERSATIONAL_KEYWORDS)

        # If there's no retrieved content and no tool results and it's neither a greeting nor a conversational question,
        # the LLM should explain that no information was found rather than hallucinate.
        if not context.retrieved and not context.tool_results and not is_greeting and not (has_history or is_convo_query):
            return "I couldn't find enough information in the connected company sources to answer that."

        rendered = PromptContextBuilder.render(context)

        try:
            response = self._provider.generate(
                rendered,
                system=context.system_policy,
            )
        except LLMProviderError as exc:
            log_event(
                logger, "llm_answerer_failed", logging.WARNING,
                exception_type=type(exc).__name__,
            )
            # Graceful degradation on transient rate limits: If actual document content was successfully retrieved,
            # present the verified data directly so the user is never blocked by external AI provider traffic.
            if "rate limited" in str(exc).lower():
                parts: list[str] = []
                for item in context.retrieved:
                    val = item.value.strip()
                    if val and not any(p in val.lower() for p in ("not configured", "couldn't find", "could not find")):
                        parts.append(val)
                for item in context.tool_results:
                    val = str(item.value).strip()
                    if val and not any(p in val.lower() for p in ("not configured", "couldn't find", "could not find")):
                        parts.append(val)
                if parts:
                    return "\n\n".join(parts)
            return f"I was unable to process your request: {exc}"

        if not response or not response.strip():
            return "I couldn't find enough information in the connected company sources to answer that."

        return response.strip()
