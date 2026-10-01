from __future__ import annotations
import re
import logging

from backend.observability.logging import log_event

logger = logging.getLogger(__name__)
from dataclasses import dataclass


class PromptInjectionDetected(ValueError):
    pass


@dataclass(frozen=True)
class GuardedContent:
    content: str
    untrusted: bool = True
    injection_detected: bool = False
    reasons: tuple[str, ...] = ()


class PromptInjectionDetector:
    """Heuristic detector used as a defense-in-depth signal, never as authorization."""
    PATTERNS = (
        (re.compile(r"ignore\s+(?:(?:all|any)\s+)?(?:previous|prior|these|the)\s+instructions", re.I), "instruction_override"),
        (re.compile(r"ignore\s+(?:the\s+)?system\s+(?:policy|instructions|message)", re.I), "system_override"),
        (re.compile(r"(system|developer)\s+(prompt|message)\s*[:=]", re.I), "prompt_disclosure"),
        (re.compile(r"reveal\s+(the\s+)?(password|secret|api\s*key|token|credential)", re.I), "secret_request"),
        (re.compile(r"you\s+are\s+now\s+(an?|the)\s+", re.I), "role_hijack"),
        (re.compile(r"execute\s+(this|the)\s+(command|tool|function)", re.I), "tool_command"),
        (re.compile(r"send\s+(?:this|the)\s+data\s+to|send\s+secrets\s+to|exfiltrat", re.I), "exfiltration_request"),
        (re.compile(r"<\s*(?:system_policy|system|developer)[^>]*>", re.I), "policy_markup_injection"),
    )

    def inspect(self, text: str) -> GuardedContent:
        reasons = tuple(reason for pattern, reason in self.PATTERNS if pattern.search(text or ""))
        return GuardedContent(text, True, bool(reasons), reasons)

    def reject_direct_instruction(self, text: str) -> None:
        result = self.inspect(text)
        if result.injection_detected:
            log_event(logger, "security_prompt_injection_detected", logging.WARNING,
                      reason_codes=result.reasons, input_length=len(text or ""))
            raise PromptInjectionDetected("Potential prompt injection detected")


class UntrustedContentGuard:
    """Wraps retrieved content so downstream prompts can distinguish data from instructions."""
    def __init__(self, detector: PromptInjectionDetector | None = None) -> None:
        self.detector = detector or PromptInjectionDetector()

    def wrap(self, content: str) -> GuardedContent:
        return self.detector.inspect(content)
