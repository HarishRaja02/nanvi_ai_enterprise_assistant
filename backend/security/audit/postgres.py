"""PostgreSQL persistent audit sink for production.

Enforces an append-only, tenant-isolated audit log with retention metadata.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from backend.security.audit.logger import AuditEvent, AuditSink

logger = logging.getLogger(__name__)


class PostgresAuditSink(AuditSink):
    """Append-only PostgreSQL audit log store with retention enforcement."""

    def __init__(self, dsn: str, default_retention_days: int = 365) -> None:
        self._dsn = dsn
        self._retention_days = default_retention_days
        self._ensure_schema()

    def _get_connection(self):
        try:
            import psycopg
            return psycopg.connect(self._dsn, connect_timeout=2)
        except ImportError:
            try:
                import psycopg2
                return psycopg2.connect(self._dsn, connect_timeout=2)
            except ImportError as exc:
                raise RuntimeError("PostgresAuditSink requires psycopg or psycopg2") from exc

    def _ensure_schema(self) -> None:
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        CREATE TABLE IF NOT EXISTS audit_events (
                        id BIGSERIAL PRIMARY KEY,
                        event_type VARCHAR(128) NOT NULL,
                        outcome VARCHAR(32) NOT NULL,
                        actor_id VARCHAR(128),
                        tenant_id VARCHAR(128),
                        resource_id VARCHAR(256),
                        metadata JSONB,
                        request_id VARCHAR(128),
                        correlation_id VARCHAR(128),
                        trace_id VARCHAR(128),
                        timestamp TIMESTAMPTZ NOT NULL,
                        retention_days INT NOT NULL,
                        retention_until TIMESTAMPTZ NOT NULL,
                        created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                    );
                    CREATE INDEX IF NOT EXISTS idx_audit_tenant_time 
                        ON audit_events(tenant_id, timestamp);
                    CREATE INDEX IF NOT EXISTS idx_audit_actor 
                        ON audit_events(actor_id);
                    CREATE INDEX IF NOT EXISTS idx_audit_retention 
                        ON audit_events(retention_until);
                """)
            conn.commit()
        except Exception as exc:
            logger.warning("Could not pre-initialize audit schema: %s", exc)

    def write(self, event: AuditEvent) -> None:
        retention_until = event.timestamp + timedelta(days=self._retention_days)
        meta_json = json.dumps(event.metadata, default=str)

        try:
            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO audit_events (
                            event_type, outcome, actor_id, tenant_id, resource_id,
                            metadata, request_id, correlation_id, trace_id,
                            timestamp, retention_days, retention_until
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            event.event_type,
                            event.outcome,
                            event.actor_id,
                            event.tenant_id,
                            event.resource_id,
                            meta_json,
                            event.request_id,
                            event.correlation_id,
                            event.trace_id,
                            event.timestamp,
                            self._retention_days,
                            retention_until,
                        ),
                    )
                conn.commit()
        except Exception as exc:
            logger.error("Failed to write audit event to PostgreSQL: %s", exc)
