"""Persistent User Query and System Answer Log Store.

Supports Supabase Cloud PostgreSQL with local SQLite resilience.
"""
from __future__ import annotations

import logging
import os
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.core.config import settings

logger = logging.getLogger(__name__)


@dataclass
class UserLogEntry:
    id: str
    user_id: str
    user_name: str
    user_role: str
    tenant_id: str
    query: str
    answer: str
    capability: str
    model: str
    created_at: str
    log_date: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class UserLogStore:
    """Thread-safe persistent store for user query & answer logs."""

    def __init__(self, dsn: str = "", sqlite_path: str | Path | None = None) -> None:
        self._dsn = dsn
        if sqlite_path:
            self._sqlite_path = Path(sqlite_path)
        elif os.getenv("VERCEL") or os.getenv("AWS_LAMBDA_FUNCTION_NAME") or os.getenv("VERCEL_ENV"):
            self._sqlite_path = Path("/tmp/user_query_logs.sqlite3")
        else:
            self._sqlite_path = Path(__file__).resolve().parents[1] / "storage" / "user_query_logs.sqlite3"
        self._lock = threading.Lock()
        self._initialized = False
        self._memory_conn: sqlite3.Connection | None = None
        self._pool = None
        self._cached_dates: list[str] | None = None
        self._cached_dates_time: float = 0.0

        if self._dsn:
            try:
                from psycopg_pool import ConnectionPool
                from psycopg.rows import dict_row
                self._pool = ConnectionPool(
                    self._dsn,
                    min_size=1,
                    max_size=5,
                    timeout=5,
                    kwargs={"row_factory": dict_row},
                    open=True,
                )
            except Exception as exc:
                logger.warning("Could not initialize connection pool for user logs (%s); fallback to direct connect.", exc)
                self._pool = None

    def _table_name(self, conn: Any = None) -> str:
        if conn is not None and isinstance(conn, sqlite3.Connection):
            return "user_query_logs"
        return "public.user_query_logs" if (self._pool or self._dsn) else "user_query_logs"

    @property
    def _table(self) -> str:
        return self._table_name()

    @contextmanager
    def _connect(self):
        if self._pool:
            try:
                with self._pool.connection() as conn:
                    yield conn
                return
            except Exception as exc:
                logger.warning("Pooled PostgreSQL query failed (%s); trying direct connection.", exc)
                self._pool = None

        if self._dsn:
            try:
                import psycopg
                from psycopg.rows import dict_row
                with psycopg.connect(self._dsn, row_factory=dict_row, connect_timeout=1) as conn:
                    yield conn
                return
            except Exception as exc:
                logger.warning("PostgreSQL user logs connection failed (%s); falling back to local SQLite.", exc)
                self._dsn = ""
                self._pool = None

        try:
            self._sqlite_path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(self._sqlite_path, timeout=10)
        except Exception as exc:
            logger.warning("SQLite storage file %s failed (%s); using in-memory store.", self._sqlite_path, exc)
            if self._memory_conn is None:
                self._memory_conn = sqlite3.connect(":memory:", check_same_thread=False)
                self._memory_conn.row_factory = sqlite3.Row
            conn = self._memory_conn

        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA journal_mode=WAL")
        except Exception:
            pass

        try:
            with conn:
                yield conn
        finally:
            if conn != self._memory_conn:
                conn.close()

    def initialize(self) -> None:
        with self._lock:
            if self._initialized:
                return
            try:
                with self._connect() as conn:
                    tbl = self._table_name(conn)
                    if self._dsn and not isinstance(conn, sqlite3.Connection):
                        conn.execute(
                            f"""
                            CREATE TABLE IF NOT EXISTS {tbl} (
                                id TEXT PRIMARY KEY,
                                user_id TEXT NOT NULL,
                                user_name TEXT,
                                user_role TEXT,
                                tenant_id TEXT NOT NULL DEFAULT 'enterprise-tenant',
                                query TEXT NOT NULL,
                                answer TEXT NOT NULL,
                                capability TEXT,
                                model TEXT,
                                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                                log_date VARCHAR(10) NOT NULL
                            );
                            CREATE INDEX IF NOT EXISTS idx_uql_date ON {tbl}(log_date);
                            CREATE INDEX IF NOT EXISTS idx_uql_created_at ON {tbl}(created_at DESC);
                            CREATE INDEX IF NOT EXISTS idx_uql_user ON {tbl}(user_id);
                            """
                        )
                        conn.commit()
                    else:
                        conn.executescript(
                            f"""
                            CREATE TABLE IF NOT EXISTS {tbl} (
                                id TEXT PRIMARY KEY,
                                user_id TEXT NOT NULL,
                                user_name TEXT,
                                user_role TEXT,
                                tenant_id TEXT NOT NULL DEFAULT 'enterprise-tenant',
                                query TEXT NOT NULL,
                                answer TEXT NOT NULL,
                                capability TEXT,
                                model TEXT,
                                created_at TEXT NOT NULL,
                                log_date TEXT NOT NULL
                            );
                            CREATE INDEX IF NOT EXISTS idx_uql_date ON {tbl}(log_date);
                            CREATE INDEX IF NOT EXISTS idx_uql_created_at ON {tbl}(created_at DESC);
                            CREATE INDEX IF NOT EXISTS idx_uql_user ON {tbl}(user_id);
                            """
                        )
                self._initialized = True
            except Exception as exc:
                logger.error("Failed to initialize user query log store: %s", exc)

    def record_log(
        self,
        user_id: str,
        user_name: str | None,
        user_role: str | None,
        query: str,
        answer: str,
        capability: str | None = None,
        model: str | None = None,
        tenant_id: str = "enterprise-tenant",
    ) -> str:
        """Record a single user query and assistant response."""
        self.initialize()
        log_id = uuid.uuid4().hex
        now = datetime.now(timezone.utc)
        created_at_str = now.isoformat()
        # Format DD-MM-YYYY (e.g. 02-11-2026)
        log_date = now.strftime("%d-%m-%Y")

        try:
            with self._connect() as conn:
                tbl = self._table_name(conn)
                if self._dsn and not isinstance(conn, sqlite3.Connection):
                    conn.execute(
                        f"""
                        INSERT INTO {tbl} (
                            id, user_id, user_name, user_role, tenant_id,
                            query, answer, capability, model, created_at, log_date
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            log_id,
                            user_id or "unknown",
                            user_name or user_id or "User",
                            user_role or "Employee",
                            tenant_id or "enterprise-tenant",
                            query or "",
                            answer or "",
                            capability or "",
                            model or getattr(settings, "llm_model", "llama-3.3-70b-versatile"),
                            now,
                            log_date,
                        ),
                    )
                    conn.commit()
                else:
                    conn.execute(
                        f"""
                        INSERT INTO {tbl} (
                            id, user_id, user_name, user_role, tenant_id,
                            query, answer, capability, model, created_at, log_date
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            log_id,
                            user_id or "unknown",
                            user_name or user_id or "User",
                            user_role or "Employee",
                            tenant_id or "enterprise-tenant",
                            query or "",
                            answer or "",
                            capability or "",
                            model or getattr(settings, "llm_model", "llama-3.3-70b-versatile"),
                            created_at_str,
                            log_date,
                        ),
                    )
                    conn.commit()
            with self._lock:
                if self._cached_dates is not None and log_date not in self._cached_dates:
                    self._cached_dates.insert(0, log_date)
            return log_id
        except Exception as exc:
            logger.error("Failed to insert user query log: %s", exc)
            return ""

    def get_available_dates(self) -> list[str]:
        """Return distinct dates (DD-MM-YYYY) in descending order, guaranteeing today is included."""
        today = datetime.now(timezone.utc).strftime("%d-%m-%Y")
        now_ts = time.time()
        with self._lock:
            if self._cached_dates is not None and (now_ts - self._cached_dates_time < 30.0):
                if today not in self._cached_dates:
                    self._cached_dates.insert(0, today)
                return list(self._cached_dates)

        self.initialize()
        dates: set[str] = {today}

        try:
            with self._connect() as conn:
                tbl = self._table_name(conn)
                cursor = conn.cursor()
                cursor.execute(f"SELECT DISTINCT log_date FROM {tbl}")
                rows = cursor.fetchall()
                for row in rows:
                    val = row["log_date"] if isinstance(row, dict) or hasattr(row, "keys") else row[0]
                    if val:
                        dates.add(str(val).strip())
        except Exception as exc:
            logger.warning("Could not fetch available log dates: %s", exc)

        def _parse_date_key(d_str: str):
            try:
                # Format: DD-MM-YYYY
                parts = d_str.split("-")
                if len(parts) == 3:
                    day, month, year = int(parts[0]), int(parts[1]), int(parts[2])
                    return (year, month, day)
            except Exception:
                pass
            return (0, 0, 0)

        # Sort descending by date (newest first)
        sorted_dates = sorted(dates, key=_parse_date_key, reverse=True)
        with self._lock:
            self._cached_dates = list(sorted_dates)
            self._cached_dates_time = now_ts
        return sorted_dates

    def get_logs(
        self,
        date: str | None = None,
        search: str | None = None,
        user_id: str | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> tuple[list[UserLogEntry], int]:
        """Fetch logs matching filters."""
        self.initialize()
        logs: list[UserLogEntry] = []
        total = 0

        conditions: list[str] = []
        params: list[Any] = []

        if date and date.lower() != "all":
            if self._dsn:
                conditions.append("log_date = %s")
            else:
                conditions.append("log_date = ?")
            params.append(date.strip())

        if user_id:
            if self._dsn:
                conditions.append("user_id = %s")
            else:
                conditions.append("user_id = ?")
            params.append(user_id.strip())

        if search:
            s = f"%{search.strip()}%"
            if self._dsn:
                conditions.append("(query ILIKE %s OR answer ILIKE %s OR user_id ILIKE %s OR user_name ILIKE %s)")
                params.extend([s, s, s, s])
            else:
                conditions.append("(query LIKE ? OR answer LIKE ? OR user_id LIKE ? OR user_name LIKE ?)")
                params.extend([s, s, s, s])

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        try:
            with self._connect() as conn:
                tbl = self._table_name(conn)
                is_pg = bool(self._dsn) and not isinstance(conn, sqlite3.Connection)
                cursor = conn.cursor()
                # 1. Total count
                count_query = f"SELECT COUNT(*) AS total_count FROM {tbl} {where_clause}"
                cursor.execute(count_query, params)
                c_row = cursor.fetchone()
                total = 0
                if c_row:
                    try:
                        total = int(c_row[0])
                    except Exception:
                        total = int(c_row["total_count"]) if hasattr(c_row, "__getitem__") else 0

                # 2. Page of records
                order_limit = "ORDER BY created_at DESC"
                if is_pg:
                    fetch_query = f"SELECT * FROM {tbl} {where_clause} {order_limit} LIMIT %s OFFSET %s"
                    cursor.execute(fetch_query, [*params, limit, offset])
                else:
                    fetch_query = f"SELECT * FROM {tbl} {where_clause} {order_limit} LIMIT ? OFFSET ?"
                    cursor.execute(fetch_query, [*params, limit, offset])

                rows = cursor.fetchall()
                for row in rows:
                    r_dict = dict(row) if hasattr(row, "keys") else {
                        "id": row[0], "user_id": row[1], "user_name": row[2], "user_role": row[3],
                        "tenant_id": row[4], "query": row[5], "answer": row[6], "capability": row[7],
                        "model": row[8], "created_at": str(row[9]), "log_date": row[10],
                    }
                    created_at_raw = r_dict.get("created_at")
                    created_at_str = created_at_raw.isoformat() if hasattr(created_at_raw, "isoformat") else str(created_at_raw)
                    logs.append(
                        UserLogEntry(
                            id=str(r_dict.get("id", "")),
                            user_id=str(r_dict.get("user_id", "")),
                            user_name=str(r_dict.get("user_name", "") or r_dict.get("user_id", "")),
                            user_role=str(r_dict.get("user_role", "") or "Employee"),
                            tenant_id=str(r_dict.get("tenant_id", "enterprise-tenant")),
                            query=str(r_dict.get("query", "")),
                            answer=str(r_dict.get("answer", "")),
                            capability=str(r_dict.get("capability", "")),
                            model=str(r_dict.get("model", "")),
                            created_at=created_at_str,
                            log_date=str(r_dict.get("log_date", "")),
                        )
                    )
        except Exception as exc:
            logger.error("Failed to query user query logs: %s", exc)

        return logs, total


_user_log_store: UserLogStore | None = None
_store_lock = threading.Lock()


def get_user_log_store() -> UserLogStore:
    global _user_log_store
    if _user_log_store is None:
        with _store_lock:
            if _user_log_store is None:
                dsn = settings.supabase_database_url or settings.database_url
                _user_log_store = UserLogStore(dsn=dsn)
    return _user_log_store
