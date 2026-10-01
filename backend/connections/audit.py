"""Connection-specific audit event writer.

Writes append-only events to the ``connection_audit_events`` table and also
routes them through the existing ``AuditLogger`` for unified observability.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from backend.connections.redaction import redact_dict
from backend.observability.logging import log_event

logger = logging.getLogger(__name__)


class ConnectionEventType:
    CREATED = "CONNECTION_CREATED"
    UPDATED = "CONNECTION_UPDATED"
    TESTED = "CONNECTION_TESTED"
    DISCONNECTED = "CONNECTION_DISCONNECTED"
    OAUTH_CONNECTED = "OAUTH_CONNECTED"
    OAUTH_REAUTHORIZED = "OAUTH_REAUTHORIZED"
    OAUTH_REVOKED = "OAUTH_REVOKED"
    CREDENTIAL_ROTATED = "CREDENTIAL_ROTATED"
    ACCESS_DENIED = "CONNECTION_ACCESS_DENIED"
    USED_BY_AGENT = "CONNECTION_USED_BY_AGENT"


class ConnectionAuditWriter:
    """Writes connection audit events to the database and logs."""

    def __init__(self, database_url: str = "") -> None:
        self._database_url = database_url

    def record(
        self,
        event: str,
        *,
        tenant_id: str,
        actor_user_id: str | None = None,
        connection_id: str | None = None,
        provider: str | None = None,
        safe_metadata: dict[str, Any] | None = None,
        ip: str | None = None,
    ) -> None:
        """Write an audit event.  Metadata is redacted automatically."""
        cleaned = redact_dict(safe_metadata or {})

        # Log through structured observability
        log_event(
            logger,
            "connection_audit",
            event_type=event,
            tenant_id=tenant_id,
            actor_user_id=actor_user_id,
            connection_id=connection_id,
            provider=provider,
            audit_metadata=cleaned,
        )

        # Persist to database if available
        if self._database_url:
            try:
                self._write_to_db(
                    event=event,
                    tenant_id=tenant_id,
                    actor_user_id=actor_user_id,
                    connection_id=connection_id,
                    provider=provider,
                    safe_metadata=cleaned,
                    ip=ip,
                )
            except Exception as exc:
                logger.warning("Could not write connection audit event to DB: %s", type(exc).__name__)

    def _write_to_db(
        self,
        *,
        event: str,
        tenant_id: str,
        actor_user_id: str | None,
        connection_id: str | None,
        provider: str | None,
        safe_metadata: dict[str, Any],
        ip: str | None,
    ) -> None:
        import json
        import uuid
        import psycopg
        event_id = str(uuid.uuid4())
        with psycopg.connect(self._database_url, autocommit=True, connect_timeout=3) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO public.connection_audit_events
                        (id, tenant_id, actor_user_id, connection_id, provider, event, safe_metadata, ip)
                    VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s)
                    """,
                    (
                        event_id,
                        tenant_id,
                        actor_user_id,
                        connection_id,
                        provider,
                        event,
                        json.dumps(safe_metadata),
                        ip,
                    ),
                )
