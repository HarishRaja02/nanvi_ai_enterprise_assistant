"""Provider-neutral LLM base class.

Subclasses implement ``_call_api`` for provider-specific HTTP calls.
The base class handles structured prompt rendering, classification, and
safe error handling.  Credentials never leave the provider layer.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any

from backend.agents.models import Capability
from backend.observability.logging import log_event

logger = logging.getLogger(__name__)


class LLMProviderError(RuntimeError):
    """Non-secret error surfaced to callers when the LLM request fails."""


class LLMNotConfiguredError(LLMProviderError):
    """Raised when required LLM credentials are missing."""


class BaseLLMProvider(ABC):
    """Provider-neutral LLM interface.

    Subclasses must implement ``_call_api`` which performs the actual HTTP
    request to the provider's chat-completions endpoint.

    This class deliberately never:
    - stores API keys in graph/orchestration state
    - logs API keys
    - includes API keys in prompts or responses
    """

    def __init__(self, model: str) -> None:
        self.model = model

    def generate(
        self,
        prompt: str,
        *,
        system: str | None = None,
        messages_history: tuple[dict[str, str], ...] | list[dict[str, str]] | None = None,
    ) -> str:
        """Generate a chat-completion response.

        Parameters
        ----------
        prompt : str
            The user/context prompt (rendered PromptContext).
        system : str | None
            Optional system message.
        messages_history : list or tuple of dicts, optional
            Optional conversation history turns with 'role' and 'content'.

        Returns
        -------
        str
            The assistant response text.
        """
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        if messages_history:
            for m in messages_history:
                role = m.get("role", "user")
                if role not in ("user", "assistant", "system"):
                    role = "user"
                messages.append({"role": role, "content": str(m.get("content", ""))})
        messages.append({"role": "user", "content": prompt})
        try:
            return self._call_api(messages)
        except LLMProviderError:
            raise
        except Exception as exc:
            # Log type only — never log secrets, tokens, or full exception text
            # that might contain credential fragments from HTTP libraries.
            log_event(
                logger, "llm_provider_failed", logging.ERROR,
                provider=self.__class__.__name__,
                model=self.model,
                exception_type=type(exc).__name__,
            )
            raise LLMProviderError("AI service request failed") from exc

    _PRONOUNS_AND_ANAPHORA = frozenset({
        "it", "its", "they", "them", "their", "theirs", "this", "that", "these", "those",
        "he", "him", "his", "she", "her", "hers", "why", "how", "what", "which",
    })

    def contextualize_query(self, query: str, history: list[Any] | tuple[Any, ...]) -> str:
        """Reformulate a follow-up query into a standalone query using conversation history.

        Preserves chat-specific context and resolves pronouns (e.g. 'Why is it useful?' ->
        'Why is Retrieval-Augmented Generation useful?').
        """
        if not history:
            return query

        query_clean = query.strip()
        words = {w.strip("?,.!;:\"'").casefold() for w in query_clean.split()}

        # Check if conversational context or anaphora resolution is relevant
        has_anaphora = bool(words.intersection(self._PRONOUNS_AND_ANAPHORA))
        is_short = len(query_clean.split()) <= 8
        is_meta_question = any(k in query_clean.casefold() for k in ("what was my", "first question", "previous question", "what did i", "what did we"))

        if is_meta_question:
            return query_clean

        if not (has_anaphora or is_short):
            return query_clean

        # Fast local pronoun resolution to prevent unnecessary LLM round-trips and avoid rate limits
        last_user_query = ""
        for msg in reversed(list(history)):
            if getattr(msg, "role", "") == "user":
                last_user_query = getattr(msg, "content", "").strip()
                break

        if last_user_query:
            import re
            topic = last_user_query.strip("?.! ")
            for prefix in (
                "what is a ", "what is an ", "what is the ", "what is ",
                "what are ", "who is ", "tell me about ", "explain ",
                "how does ", "how do ", "why is ", "why are "
            ):
                if topic.lower().startswith(prefix):
                    topic = topic[len(prefix):].strip()
                    break
            if topic and len(topic) >= 2:
                pronoun_pattern = re.compile(r'\b(it|this|that|they|them)\b', re.IGNORECASE)
                if pronoun_pattern.search(query_clean):
                    heuristic_rewritten = pronoun_pattern.sub(topic, query_clean)
                    if heuristic_rewritten != query_clean:
                        return heuristic_rewritten

        # Format the last 2-4 turns of history
        history_lines: list[str] = []
        for msg in list(history)[-4:]:
            role = getattr(msg, "role", "user")
            content = getattr(msg, "content", "")
            preview = content[:200] if len(content) > 200 else content
            history_lines.append(f"{role.capitalize()}: {preview}")

        history_text = "\n".join(history_lines)
        system = (
            "You are a search query reformulation specialist for enterprise AI. "
            "Given the chat history and a follow-up question, rewrite the follow-up question into a standalone, complete question "
            "that resolves all pronouns (such as 'it', 'they', 'this', 'that') and includes the exact subject being discussed. "
            "Do NOT answer the question. Respond with ONLY the reformulated question string. No quotes, no intro."
        )
        prompt = (
            f"Chat History:\n{history_text}\n\n"
            f"Follow-up Question: {query_clean}\n\n"
            f"Standalone Question:"
        )

        try:
            reformulated = self.generate(prompt, system=system).strip().strip('"').strip("'")
            if reformulated and len(reformulated) >= 3 and "\n" not in reformulated:
                return reformulated
        except Exception as exc:
            logger.debug("LLM contextualize_query failed, fallback to original query: %s", exc)

        return query_clean

    def classify(self, query: str, capabilities: tuple[Capability, ...]) -> Capability:
        """Classify a user query into a capability using the LLM.

        This is an advisory classification only — it never grants permissions.
        Authorization is enforced independently by the Tool Gateway.
        """
        capability_names = ", ".join(c.value for c in capabilities)
        system = (
            "You are a classifier. Given a user query and a list of capabilities, "
            "respond with ONLY the single most relevant capability name. "
            "Do not explain. Do not add punctuation."
        )
        prompt = (
            f"Capabilities: {capability_names}\n\n"
            f"User query: {query}\n\n"
            f"Respond with exactly one capability name from the list above."
        )
        try:
            result = self.generate(prompt, system=system).strip().lower()
            for cap in capabilities:
                if cap.value == result:
                    return cap
            # Fallback if LLM returned something unexpected
            return Capability.KNOWLEDGE
        except LLMProviderError:
            return Capability.KNOWLEDGE

    @abstractmethod
    def _call_api(self, messages: list[dict[str, str]]) -> str:
        """Provider-specific API call. Must return the assistant content string.

        Implementations must:
        - Use server-side credentials only
        - Never include credentials in the returned string
        - Raise ``LLMProviderError`` on failure
        """
        raise NotImplementedError
