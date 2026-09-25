from __future__ import annotations

from backend.security.audit.logger import AuditEvent, AuditSink


class InMemoryAuditSink(AuditSink):
    """Test/development sink only. Do not treat it as an enterprise audit store."""

    def __init__(self) -> None:
        self.events: list[AuditEvent] = []

    def write(self, event: AuditEvent) -> None:
        self.events.append(event)
