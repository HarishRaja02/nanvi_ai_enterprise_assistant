from __future__ import annotations

import json
import logging
import re
import sys
from contextvars import ContextVar, Token
from datetime import date, datetime
from typing import Any, Mapping
from uuid import uuid4

_request_id: ContextVar[str] = ContextVar("request_id", default="-")
_correlation_id: ContextVar[str] = ContextVar("correlation_id", default="-")
_trace_id: ContextVar[str] = ContextVar("trace_id", default="-")

_SECRET_KEY_RE = re.compile(
    r"(?i)(password|passwd|passphrase|secret|api[_-]?key|access[_-]?token|refresh[_-]?token|authorization|cookie|private[_-]?key|client[_-]?secret)"
)
_SECRET_ASSIGNMENT_RE = re.compile(
    r"(?i)\b(password|passwd|secret|api[_ -]?key|access[_ -]?token|refresh[_ -]?token)\s*[:=]\s*[^\s,;]+"
)
_BEARER_RE = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+\-/]+=*")
_WINDOWS_PATH_RE = re.compile(r"\b[A-Za-z]:\\[^\r\n]*")


def _safe_scalar(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, str):
        value = _BEARER_RE.sub("Bearer [REDACTED]", value)
        value = _SECRET_ASSIGNMENT_RE.sub(lambda m: f"{m.group(1)}=[REDACTED]", value)
        value = _WINDOWS_PATH_RE.sub("[REDACTED_PATH]", value)
        return value[:4000]
    return str(value)[:4000]


def sanitize(value: Any, *, key: str | None = None) -> Any:
    """Recursively remove credentials and excessive sensitive payloads from logs."""
    if key and _SECRET_KEY_RE.search(key):
        return "[REDACTED]"
    if isinstance(value, Mapping):
        return {str(k): sanitize(v, key=str(k)) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [sanitize(v) for v in value]
    return _safe_scalar(value)


def set_request_context(request_id: str, correlation_id: str, trace_id: str | None = None) -> tuple[Token, Token, Token]:
    return (
        _request_id.set(request_id),
        _correlation_id.set(correlation_id),
        _trace_id.set(trace_id or uuid4().hex),
    )


def reset_request_context(tokens: tuple[Token, Token, Token]) -> None:
    _request_id.reset(tokens[0])
    _correlation_id.reset(tokens[1])
    _trace_id.reset(tokens[2])


def set_request_id(value: str) -> None:
    _request_id.set(value)


def get_request_id() -> str:
    return _request_id.get()


def get_correlation_id() -> str:
    return _correlation_id.get()


def get_trace_id() -> str:
    return _trace_id.get()


def log_event(logger: logging.Logger, event: str, level: int = logging.INFO, **fields: Any) -> None:
    payload = {
        "event": event,
        **sanitize(fields),
        # Correlation fields are always authoritative from the current request context.
        "request_id": get_request_id(),
        "correlation_id": get_correlation_id(),
        "trace_id": get_trace_id(),
    }
    logger.log(level, json.dumps(payload, separators=(",", ":"), sort_keys=True, default=str))


class JsonFormatter(logging.Formatter):
    """JSON formatter with a final defense-in-depth secret scrub."""

    def format(self, record: logging.LogRecord) -> str:
        raw_message = record.getMessage()
        event_fields: dict[str, Any] = {}
        try:
            parsed = json.loads(raw_message)
            if isinstance(parsed, dict) and "event" in parsed:
                event_fields = parsed
            else:
                event_fields = {"message": raw_message}
        except (TypeError, ValueError):
            event_fields = {"message": raw_message}
        payload = {
            "timestamp": datetime.fromtimestamp(record.created).astimezone().isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "request_id": getattr(record, "request_id", get_request_id()),
            "correlation_id": getattr(record, "correlation_id", get_correlation_id()),
            "trace_id": getattr(record, "trace_id", get_trace_id()),
            **event_fields,
        }
        if record.exc_info:
            payload["exception_type"] = type(record.exc_info[1]).__name__ if record.exc_info[1] else "Exception"
        return json.dumps(sanitize(payload), separators=(",", ":"), sort_keys=True, default=str)


def configure_logging(level: str = "INFO") -> None:
    class ContextFilter(logging.Filter):
        def filter(self, record: logging.LogRecord) -> bool:
            record.request_id = get_request_id()
            record.correlation_id = get_correlation_id()
            record.trace_id = get_trace_id()
            return True

    handler = logging.StreamHandler(sys.stdout)
    handler.addFilter(ContextFilter())
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    logging.captureWarnings(True)
