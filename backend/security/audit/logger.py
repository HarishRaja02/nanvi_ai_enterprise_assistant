from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
import logging

from backend.observability.logging import (
    get_correlation_id,
    get_request_id,
    get_trace_id,
    log_event,
    sanitize,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AuditEvent:
    event_type: str
    outcome: str
    actor_id: str | None
    tenant_id: str | None
    resource_id: str | None
    timestamp: datetime
    metadata: dict[str, Any]
    request_id: str = "-"
    correlation_id: str = "-"
    trace_id: str = "-"


class AuditSink(ABC):
    @abstractmethod
    def write(self, event: AuditEvent) -> None:
        raise NotImplementedError


class AuditLogger:
    """Structured audit facade with automatic correlation and secret scrubbing."""

    def __init__(self, sink: AuditSink) -> None:
        self._sink = sink

    def record(
        self,
        event_type: str,
        outcome: str,
        actor_id: str | None = None,
        tenant_id: str | None = None,
        resource_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        safe_metadata = sanitize(metadata or {})
        event = AuditEvent(
            event_type=event_type,
            outcome=outcome,
            actor_id=actor_id,
            tenant_id=tenant_id,
            resource_id=resource_id,
            timestamp=datetime.now(timezone.utc),
            metadata=safe_metadata,
            request_id=get_request_id(),
            correlation_id=get_correlation_id(),
            trace_id=get_trace_id(),
        )
        self._sink.write(event)
        log_event(
            logger,
            "audit_event",
            event_type=event_type,
            outcome=outcome,
            actor_id=actor_id,
            tenant_id=tenant_id,
            resource_id=resource_id,
            audit_metadata=safe_metadata,
        )
