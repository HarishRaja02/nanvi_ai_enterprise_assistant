from __future__ import annotations
import re
from dataclasses import dataclass
from typing import Any


class OutputValidationError(ValueError):
    pass


@dataclass(frozen=True)
class SanitizedOutput:
    value: Any
    redacted: bool
    reasons: tuple[str, ...] = ()


class SensitiveDataFilter:
    """Defense-in-depth output filter. Authorization remains the primary boundary."""
    PATTERNS = (
        (re.compile(r"(?i)\b(?:sk|ghp|github_pat|xox[baprs]-)[A-Za-z0-9_\-]{16,}\b"), "credential_like_token"),
        (re.compile(r"(?i)\b(?:api[_ -]?key|secret|client[_ -]?secret|password|passwd|access[_ -]?token)\s*[:=]\s*[^\s,;]+"), "secret_assignment"),
        (re.compile(r"\b[A-Za-z]:\\[^\r\n]*"), "windows_path"),
        (re.compile(r"(?i)\b(?:SELECT|INSERT|UPDATE|DELETE|DROP|ALTER|TRUNCATE)\b[\s\S]{0,500}"), "sql_statement"),
    )

    def sanitize_text(self, text: str) -> SanitizedOutput:
        result = text
        reasons: list[str] = []
        for pattern, reason in self.PATTERNS:
            new = pattern.sub("[REDACTED]", result)
            if new != result:
                reasons.append(reason)
                result = new
        return SanitizedOutput(result, bool(reasons), tuple(sorted(set(reasons))))

    def validate_public_output(self, value: Any) -> Any:
        if isinstance(value, str):
            return self.sanitize_text(value).value
        if isinstance(value, dict):
            return {str(k): self.validate_public_output(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return type(value)(self.validate_public_output(v) for v in value)
        return value
