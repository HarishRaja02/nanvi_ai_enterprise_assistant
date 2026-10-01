from __future__ import annotations

from backend.security.audit.logger import AuditEvent, AuditSink
from backend.core.exceptions import ConfigurationError


class InMemoryAuditSink(AuditSink):
    """Test/development sink only. Rejected at startup in production."""

    def __init__(self) -> None:
        import backend.core.config as cfg
        if cfg.settings.is_production:
            raise ConfigurationError(
                "InMemoryAuditSink is forbidden in production. Configure a durable PostgreSQL audit store."
            )
        self.events: list[AuditEvent] = []

    def write(self, event: AuditEvent) -> None:
        self.events.append(event)
