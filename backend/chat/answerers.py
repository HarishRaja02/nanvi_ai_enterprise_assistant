"""Answerers generating responses from prompt context."""
from __future__ import annotations

from abc import ABC, abstractmethod

from backend.security.ai.context import PromptContext


class ChatAnswerer(ABC):
    @abstractmethod
    def answer(self, context: PromptContext) -> str: ...


class DeterministicTestAnswerer(ChatAnswerer):
    """Test-only answerer. It deliberately does not pretend to be a production LLM."""

    _GREETINGS = frozenset({
        "hi", "hello", "hey", "hola", "namaste",
        "good morning", "good afternoon", "good evening",
        "greetings", "help", "who are you", "what can you do",
        "what are you", "how are you", "hi nanvi", "hello nanvi",
    })

    def answer(self, context: PromptContext) -> str:
        query_norm = context.user.value.strip().casefold().rstrip("!?.,")
        if query_norm in self._GREETINGS:
            return "Hello! I'm Nanvi, your enterprise assistant. Ask me about company files, email, operational data, or reports you're authorized to access."
        if not context.retrieved and not context.tool_results:
            return "I couldn't find any authorized information matching your request."
        parts: list[str] = []
        for item in context.retrieved:
            parts.append(item.value)
        for item in context.tool_results:
            content = item.value
            if hasattr(content, "explanation") and content.explanation:
                parts.append(str(content.explanation))
            elif hasattr(content, "columns") and hasattr(content, "rows") and content.columns:
                if content.rows:
                    headers = " | ".join(str(c) for c in content.columns)
                    sep = " | ".join("---" for _ in content.columns)
                    row_lines = [" | ".join(str(val) for val in row) for row in content.rows]
                    table_str = f"| {headers} |\n| {sep} |\n" + "\n".join(f"| {r} |" for r in row_lines)
                    parts.append(table_str)
                else:
                    parts.append("Database: No matching records found.")
            else:
                parts.append(str(content))
        return "\n\n".join(parts)
