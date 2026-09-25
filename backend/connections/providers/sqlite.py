"""SQLite connection provider."""
from __future__ import annotations

import logging
import os
import sqlite3
from pathlib import Path
from typing import Any

from backend.connections.base import (
    AuthType,
    BaseProvider,
    Capability,
    ConnectionError,
    InvalidCredentials,
    ProviderMetadata,
    Unreachable,
)

logger = logging.getLogger(__name__)


class SQLiteProvider(BaseProvider):
    """Provider for SQLite local or embedded database files."""

    def get_metadata(self) -> ProviderMetadata:
        return ProviderMetadata(
            id="sqlite",
            name="SQLite",
            categories=("SQL Databases",),
            icon="sqlite",
            description="Connect a SQLite embedded database file for querying and reporting.",
            auth_type=AuthType.FILESYSTEM,
            capabilities=frozenset({
                Capability.CREDENTIALS_FORM,
                Capability.TEST,
                Capability.QUERY_SQL,
            }),
            available=True,
            configuration_schema={
                "type": "object",
                "required": ["path"],
                "properties": {
                    "path": {
                        "type": "string",
                        "title": "SQLite Database Path",
                        "description": "Absolute path to SQLite .db file (e.g. C:\\data\\production.db or /var/data/app.db)",
                    },
                    "read_only": {
                        "type": "boolean",
                        "title": "Read-Only Mode",
                        "default": True,
                        "description": "Open database in read-only mode to prevent modifications",
                    },
                },
            },
        )

    def _resolve_and_verify_path(self, raw_path: str) -> Path:
        if not raw_path or not raw_path.strip():
            raise InvalidCredentials("SQLite database path is required.")

        p = Path(raw_path.strip()).resolve()
        if not p.exists():
            raise Unreachable(f"SQLite file does not exist at: {p}")
        if not p.is_file():
            raise InvalidCredentials(f"Path is not a regular file: {p}")
        if not os.access(p, os.R_OK):
            raise InvalidCredentials(f"File exists but is not readable: {p}")

        return p

    def connect(self, config: dict[str, Any]) -> dict[str, Any]:
        raw_path = config.get("path", "")
        p = self._resolve_and_verify_path(raw_path)
        read_only = bool(config.get("read_only", True))

        account_id = p.name
        display_name = f"SQLite ({p.stem})"

        return {
            "account_identifier": account_id,
            "display_name": display_name,
            "credentials": {
                "path": str(p),
                "read_only": read_only,
            },
            "metadata_safe": {
                "filename": p.name,
                "read_only": read_only,
                "size_bytes": p.stat().st_size,
            },
            "granted_scopes": ["query_sql"],
        }

    def test_connection(
        self,
        *,
        decrypted_credentials: dict[str, Any],
        metadata_safe: dict[str, Any],
    ) -> dict[str, Any]:
        raw_path = decrypted_credentials.get("path", "")
        p = self._resolve_and_verify_path(raw_path)

        conn = sqlite3.connect(f"file:{p.as_posix()}?mode=ro", uri=True, timeout=3.0)
        try:
            cur = conn.cursor()
            cur.execute("SELECT sqlite_version();")
            version = cur.fetchone()[0]
            cur.execute("PRAGMA quick_check(1);")
            integrity = cur.fetchone()[0]
            if integrity.lower() != "ok":
                raise ConnectionError(f"SQLite integrity check failed: {integrity}")
            return {"ok": True, "version": f"SQLite {version}", "integrity": integrity}
        except ConnectionError:
            raise
        except Exception as exc:
            raise ConnectionError(f"SQLite connection failed: {exc}") from exc
        finally:
            conn.close()

    def get_client(
        self,
        *,
        decrypted_credentials: dict[str, Any],
        metadata_safe: dict[str, Any],
    ) -> Any:
        db_path = decrypted_credentials.get("path", "")
        read_only = bool(decrypted_credentials.get("read_only", True))

        class SQLiteClient:
            def __init__(self, path: str, ro: bool) -> None:
                self.path = Path(path).as_posix()
                self.ro = ro

            def query(self, sql: str, params: tuple[Any, ...] | None = None) -> list[dict[str, Any]]:
                mode = "ro" if self.ro else "rw"
                conn = sqlite3.connect(f"file:{self.path}?mode={mode}", uri=True, timeout=5.0)
                conn.row_factory = sqlite3.Row
                try:
                    cur = conn.cursor()
                    cur.execute(sql, params or ())
                    rows = cur.fetchall()
                    return [dict(r) for r in rows]
                finally:
                    conn.close()

        return SQLiteClient(db_path, read_only)
