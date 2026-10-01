"""Database migration runner for the Connections Hub.

Supports PostgreSQL and SQLite fallback for local development / testing.
Applies forward migrations safely and tracks applied versions.
"""
from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import Any

from backend.core.config import settings

logger = logging.getLogger(__name__)

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "database" / "migrations" / "versions"


def run_connections_migrations(dsn: str | None = None) -> bool:
    """Run pending connections migrations against the target database.

    If dsn is empty/none, checks settings.supabase_database_url or settings.database_url.
    Returns True if migrations succeeded or DB not configured.
    """
    target_dsn = dsn or settings.supabase_database_url or settings.database_url
    if not target_dsn:
        logger.info("No PostgreSQL DSN configured. Skipping Postgres migrations.")
        return False

    try:
        import psycopg
        with psycopg.connect(target_dsn, autocommit=True, connect_timeout=5) as conn:
            with conn.cursor() as cur:
                # Ensure migration tracker exists
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS public.schema_migrations (
                        version VARCHAR(50) PRIMARY KEY,
                        applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    );
                """)
                cur.execute("SELECT version FROM public.schema_migrations;")
                applied = {row[0] for row in cur.fetchall()}

                files = [f for f in sorted(MIGRATIONS_DIR.glob("*.sql")) if not f.name.endswith("_down.sql")]
                for sql_file in files:
                    version = sql_file.stem
                    if version not in applied:
                        logger.info("Applying migration %s to PostgreSQL...", version)
                        sql = sql_file.read_text(encoding="utf-8")
                        cur.execute(sql)
                        cur.execute("INSERT INTO public.schema_migrations (version) VALUES (%s);", (version,))
                        logger.info("Applied migration %s successfully.", version)

        return True
    except Exception as exc:
        logger.warning("Failed to run PostgreSQL migrations (%s): %s", type(exc).__name__, exc)
        return False


def init_sqlite_connections_schema(conn: sqlite3.Connection) -> None:
    """Initialize connections tables in SQLite (used for local/test fallback)."""
    with conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS connections (
                id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                owner_user_id TEXT,
                scope_level TEXT NOT NULL DEFAULT 'user',
                provider TEXT NOT NULL,
                display_name TEXT NOT NULL,
                account_identifier TEXT,
                credential_type TEXT NOT NULL,
                encrypted_credentials BLOB,
                encryption_key_id TEXT,
                granted_scopes TEXT,  -- comma-separated or json
                metadata_safe TEXT DEFAULT '{}',
                status TEXT NOT NULL DEFAULT 'DISCONNECTED',
                status_reason TEXT,
                last_tested_at TEXT,
                last_used_at TEXT,
                last_synced_at TEXT,
                created_by TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now')),
                deleted_at TEXT
            );

            CREATE UNIQUE INDEX IF NOT EXISTS uix_connections_unique
                ON connections (tenant_id, provider, account_identifier, scope_level, IFNULL(owner_user_id, ''))
                WHERE deleted_at IS NULL;

            CREATE INDEX IF NOT EXISTS idx_connections_tenant_status
                ON connections (tenant_id, status) WHERE deleted_at IS NULL;

            CREATE TABLE IF NOT EXISTS oauth_states (
                state TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                tenant_id TEXT NOT NULL,
                provider TEXT NOT NULL,
                pkce_verifier TEXT,
                redirect_after TEXT,
                expires_at TEXT NOT NULL,
                consumed_at TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_oauth_states_expires ON oauth_states (expires_at);

            CREATE TABLE IF NOT EXISTS connection_audit_events (
                id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                actor_user_id TEXT,
                connection_id TEXT,
                provider TEXT,
                event TEXT NOT NULL,
                safe_metadata TEXT DEFAULT '{}',
                ip TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE INDEX IF NOT EXISTS idx_conn_audit_tenant ON connection_audit_events (tenant_id, created_at DESC);
        """)
    logger.info("Initialized connections tables in SQLite.")
