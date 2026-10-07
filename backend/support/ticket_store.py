"""Persistent Support & Trouble Ticket Store for Nanvi AI Enterprise Assistant.

Stores user-submitted trouble reports, issues, and developer troubleshooting logs.
"""
from __future__ import annotations

import json
import logging
import sqlite3
import threading
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.core.config import settings

logger = logging.getLogger(__name__)


@dataclass
class SupportTicket:
    id: str
    reporter_id: str
    reporter_name: str
    reporter_email: str
    reporter_role: str
    category: str
    severity: str
    subject: str
    description: str
    status: str
    admin_notes: str | None = None
    diagnostic_info: dict[str, Any] | None = None
    created_at: str = ""
    updated_at: str = ""


class SupportTicketStore:
    """Thread-safe persistent store for support tickets using SQLite or PostgreSQL."""

    def __init__(self, dsn: str = "", sqlite_path: str | Path | None = None) -> None:
        self._dsn = dsn
        self._sqlite_path = (
            Path(sqlite_path)
            if sqlite_path
            else Path(__file__).resolve().parents[1] / "storage" / "support_tickets.sqlite3"
        )
        self._lock = threading.Lock()
        self._initialized = False

    @property
    def _table(self) -> str:
        return "public.nanvi_support_tickets" if self._dsn else "support_tickets"

    def _connect(self):
        if self._dsn:
            try:
                import psycopg
                from psycopg.rows import dict_row
                return psycopg.connect(self._dsn, row_factory=dict_row, connect_timeout=3)
            except Exception as exc:
                logger.warning("PostgreSQL support tickets connection failed (%s); falling back to SQLite.", exc)
                self._dsn = ""

        self._sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self._sqlite_path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def initialize(self) -> None:
        with self._lock:
            if self._initialized:
                return
            with self._connect() as conn:
                if self._dsn:
                    conn.execute(
                        f"""
                        CREATE TABLE IF NOT EXISTS {self._table} (
                            id TEXT PRIMARY KEY,
                            reporter_id TEXT NOT NULL,
                            reporter_name TEXT NOT NULL,
                            reporter_email TEXT NOT NULL,
                            reporter_role TEXT NOT NULL,
                            category TEXT NOT NULL,
                            severity TEXT NOT NULL,
                            subject TEXT NOT NULL,
                            description TEXT NOT NULL,
                            status TEXT NOT NULL DEFAULT 'Open',
                            admin_notes TEXT,
                            diagnostic_info TEXT,
                            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                        )
                        """
                    )
                    conn.commit()
                else:
                    conn.execute(
                        f"""
                        CREATE TABLE IF NOT EXISTS {self._table} (
                            id TEXT PRIMARY KEY,
                            reporter_id TEXT NOT NULL,
                            reporter_name TEXT NOT NULL,
                            reporter_email TEXT NOT NULL,
                            reporter_role TEXT NOT NULL,
                            category TEXT NOT NULL,
                            severity TEXT NOT NULL,
                            subject TEXT NOT NULL,
                            description TEXT NOT NULL,
                            status TEXT NOT NULL DEFAULT 'Open',
                            admin_notes TEXT,
                            diagnostic_info TEXT,
                            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                        )
                        """
                    )
                    conn.commit()
            self._initialized = True

    def create_ticket(
        self,
        *,
        reporter_id: str,
        reporter_name: str,
        reporter_email: str,
        reporter_role: str,
        category: str,
        severity: str,
        subject: str,
        description: str,
        diagnostic_info: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self.initialize()
        ticket_id = f"TICK-{uuid.uuid4().hex[:8].upper()}"
        now_iso = datetime.now(timezone.utc).isoformat()
        diag_json = json.dumps(diagnostic_info or {})

        placeholder = "%s" if self._dsn else "?"
        sql = (
            f"INSERT INTO {self._table} "
            "(id, reporter_id, reporter_name, reporter_email, reporter_role, category, severity, subject, description, status, admin_notes, diagnostic_info, created_at, updated_at) "
            f"VALUES ({', '.join([placeholder] * 14)})"
        )
        with self._connect() as conn:
            conn.execute(
                sql,
                (
                    ticket_id,
                    reporter_id,
                    reporter_name,
                    reporter_email,
                    reporter_role,
                    category,
                    severity,
                    subject,
                    description,
                    "Open",
                    None,
                    diag_json,
                    now_iso,
                    now_iso,
                ),
            )
            conn.commit()

        return self.get_ticket(ticket_id)

    def list_tickets(self, reporter_id: str | None = None, status: str | None = None) -> list[dict[str, Any]]:
        self.initialize()
        placeholder = "%s" if self._dsn else "?"
        clauses = []
        params = []

        if reporter_id:
            clauses.append(f"reporter_id = {placeholder}")
            params.append(reporter_id)
        if status and status.lower() != "all":
            clauses.append(f"LOWER(status) = LOWER({placeholder})")
            params.append(status)

        where_clause = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = f"SELECT * FROM {self._table} {where_clause} ORDER BY created_at DESC"

        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()

        results = []
        for row in rows:
            d = dict(row)
            if d.get("diagnostic_info") and isinstance(d["diagnostic_info"], str):
                try:
                    d["diagnostic_info"] = json.loads(d["diagnostic_info"])
                except Exception:
                    d["diagnostic_info"] = {}
            results.append(d)
        return results

    def get_ticket(self, ticket_id: str) -> dict[str, Any]:
        self.initialize()
        placeholder = "%s" if self._dsn else "?"
        sql = f"SELECT * FROM {self._table} WHERE id = {placeholder}"
        with self._connect() as conn:
            row = conn.execute(sql, (ticket_id,)).fetchone()
        if not row:
            raise ValueError(f"Support ticket {ticket_id} not found.")
        d = dict(row)
        if d.get("diagnostic_info") and isinstance(d["diagnostic_info"], str):
            try:
                d["diagnostic_info"] = json.loads(d["diagnostic_info"])
            except Exception:
                d["diagnostic_info"] = {}
        return d

    def update_ticket_status(
        self, ticket_id: str, status: str, admin_notes: str | None = None
    ) -> dict[str, Any]:
        self.initialize()
        now_iso = datetime.now(timezone.utc).isoformat()
        placeholder = "%s" if self._dsn else "?"

        updates = [f"status = {placeholder}", f"updated_at = {placeholder}"]
        params = [status, now_iso]

        if admin_notes is not None:
            updates.append(f"admin_notes = {placeholder}")
            params.append(admin_notes)

        params.append(ticket_id)
        sql = f"UPDATE {self._table} SET {', '.join(updates)} WHERE id = {placeholder}"

        with self._connect() as conn:
            conn.execute(sql, params)
            conn.commit()

        return self.get_ticket(ticket_id)

    def delete_ticket(self, ticket_id: str) -> None:
        self.initialize()
        placeholder = "%s" if self._dsn else "?"
        sql = f"DELETE FROM {self._table} WHERE id = {placeholder}"
        with self._connect() as conn:
            conn.execute(sql, (ticket_id,))
            conn.commit()


_ticket_store: SupportTicketStore | None = None
_ticket_lock = threading.Lock()


def get_support_ticket_store() -> SupportTicketStore:
    global _ticket_store
    if _ticket_store is None:
        with _ticket_lock:
            if _ticket_store is None:
                dsn = settings.supabase_database_url or settings.database_url
                _ticket_store = SupportTicketStore(dsn=dsn if settings.is_production else "")
    return _ticket_store
