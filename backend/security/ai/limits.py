from __future__ import annotations
from dataclasses import dataclass


class ToolCallLimitExceeded(RuntimeError):
    pass


@dataclass
class ToolCallBudget:
    max_calls: int = 8
    calls: int = 0

    def consume(self) -> None:
        if self.calls >= self.max_calls:
            raise ToolCallLimitExceeded("Maximum tool-call budget exceeded")
        self.calls += 1


class AgentLoopGuard:
    """Detects repeated identical agent/tool actions and hard-stops cycles."""
    def __init__(self, max_steps: int = 12, max_repeated_action: int = 2) -> None:
        self.max_steps = max_steps
        self.max_repeated_action = max_repeated_action
        self.steps = 0
        self._last_action: str | None = None
        self._repeats = 0

    def observe(self, action: str) -> None:
        self.steps += 1
        if self.steps > self.max_steps:
            raise ToolCallLimitExceeded("Maximum agent steps exceeded")
        if action == self._last_action:
            self._repeats += 1
        else:
            self._last_action = action
            self._repeats = 1
        if self._repeats > self.max_repeated_action:
            raise ToolCallLimitExceeded("Repeated agent action loop detected")
