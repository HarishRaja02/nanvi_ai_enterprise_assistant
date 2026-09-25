"""Secret redaction for logs, API responses, and audit events.

Provides a logging filter and safe serializers that scrub values keyed like
``password``, ``secret``, ``token``, ``api_key``, etc.  Also catches known
secret patterns (e.g. ``ya29.*``, ``gsk_*``).
"""
from __future__ import annotations

import copy
import logging
import re
from typing import Any

# Keys whose values are always redacted (case-insensitive substring match)
_SENSITIVE_KEY_PARTS = frozenset({
    "password", "secret", "token", "authorization", "api_key", "apikey",
    "private_key", "refresh_token", "access_token", "credential", "credentials",
    "client_secret", "encryption_key", "service_key", "anon_key",
    "bearer", "dsn", "connection_string", "database_url",
})

# Regex patterns that catch known secret formats
_SECRET_PATTERNS = (
    re.compile(r"ya29\.[A-Za-z0-9_-]{20,}"),      # Google access token
    re.compile(r"1//[A-Za-z0-9_-]{20,}"),          # Google refresh token
    re.compile(r"gsk_[A-Za-z0-9]{20,}"),           # Groq API key
    re.compile(r"sk-[A-Za-z0-9]{20,}"),            # OpenAI-style key
    re.compile(r"ghp_[A-Za-z0-9]{20,}"),           # GitHub PAT
    re.compile(r"gho_[A-Za-z0-9]{20,}"),           # GitHub OAuth token
    re.compile(r"ghu_[A-Za-z0-9]{20,}"),           # GitHub user token
    re.compile(r"ghs_[A-Za-z0-9]{20,}"),           # GitHub server token
    re.compile(r"github_pat_[A-Za-z0-9]{20,}"),    # GitHub fine-grained PAT
    re.compile(r"sb_[A-Za-z0-9_]{20,}"),           # Supabase key
    re.compile(r"GOCSPX-[A-Za-z0-9_-]{20,}"),     # Google client secret
    re.compile(r"tvly-[A-Za-z0-9_-]{20,}"),        # Tavily key
    re.compile(r"eyJ[A-Za-z0-9_-]{40,}"),          # JWT-like token
)

REDACTED = "••••••••"


def _is_sensitive_key(key: str) -> bool:
    """Check if a key name indicates a sensitive value."""
    lower = key.lower().replace("-", "_")
    return any(part in lower for part in _SENSITIVE_KEY_PARTS)


def _redact_string(value: str) -> str:
    """Redact known secret patterns from a string."""
    result = value
    for pattern in _SECRET_PATTERNS:
        result = pattern.sub(REDACTED, result)
    return result


def redact_dict(data: dict[str, Any], *, deep: bool = True) -> dict[str, Any]:
    """Return a copy of *data* with sensitive values replaced by REDACTED.

    - Keys matching ``_SENSITIVE_KEY_PARTS`` have their values fully replaced.
    - String values are scanned for known secret patterns.
    - Nested dicts and lists are handled when *deep* is True.
    """
    if not isinstance(data, dict):
        return data
    out: dict[str, Any] = {}
    for key, value in data.items():
        if _is_sensitive_key(key):
            out[key] = REDACTED
        elif isinstance(value, str):
            out[key] = _redact_string(value)
        elif deep and isinstance(value, dict):
            out[key] = redact_dict(value, deep=True)
        elif deep and isinstance(value, (list, tuple)):
            out[key] = [
                redact_dict(v, deep=True) if isinstance(v, dict)
                else (_redact_string(v) if isinstance(v, str) else v)
                for v in value
            ]
        else:
            out[key] = value
    return out


def redact_value(value: Any) -> Any:
    """Redact a single value if it looks like a secret."""
    if isinstance(value, str):
        return _redact_string(value)
    if isinstance(value, dict):
        return redact_dict(value)
    return value


class SecretRedactionFilter(logging.Filter):
    """Logging filter that scrubs secret patterns from log messages and args."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = _redact_string(record.msg)
        if record.args:
            if isinstance(record.args, dict):
                record.args = {
                    k: (REDACTED if _is_sensitive_key(k) else _redact_string(str(v)) if isinstance(v, str) else v)
                    for k, v in record.args.items()
                }
            elif isinstance(record.args, tuple):
                record.args = tuple(
                    _redact_string(str(a)) if isinstance(a, str) else a
                    for a in record.args
                )
        return True
