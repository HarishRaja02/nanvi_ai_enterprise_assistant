"""PostgreSQL connection provider."""
from __future__ import annotations

import re
import urllib.parse
from typing import Any

from backend.connections.base import (
    AuthType,
    BaseProvider,
    Capability,
    ConnectionError,
    ConnectionTimeout,
    InvalidCredentials,
    ProviderMetadata,
    TlsError,
    Unreachable,
)


class PostgreSQLProvider(BaseProvider):
    """Provider for PostgreSQL databases."""

    def get_metadata(self) -> ProviderMetadata:
        return ProviderMetadata(
            id="postgresql",
            name="PostgreSQL",
            categories=("SQL Databases",),
            icon="postgresql",
            description="Connect a PostgreSQL relational database for read-only querying and reporting.",
            auth_type=AuthType.DB_PASSWORD,
            capabilities=frozenset({
                Capability.CREDENTIALS_FORM,
                Capability.TEST,
                Capability.QUERY_SQL,
            }),
            available=True,
            configuration_schema={
                "type": "object",
                "properties": {
                    "dsn": {
                        "type": "string",
                        "title": "Connection String (DSN)",
                        "description": "e.g. postgresql://user:password@localhost:5432/enterprise_db",
                    },
                    "host": {
                        "type": "string",
                        "title": "Host",
                        "default": "localhost",
                    },
                    "port": {
                        "type": "integer",
                        "title": "Port",
                        "default": 5432,
                    },
                    "database": {
                        "type": "string",
                        "title": "Database Name",
                    },
                    "user": {
                        "type": "string",
                        "title": "Username",
                    },
                    "password": {
                        "type": "string",
                        "title": "Password",
                        "format": "password",
                    },
                    "sslmode": {
                        "type": "string",
                        "title": "SSL Mode",
                        "enum": ["prefer", "require", "verify-ca", "verify-full", "disable"],
                        "default": "prefer",
                    },
                },
            },
        )

    def _build_dsn(self, config: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        dsn = config.get("dsn", "").strip()
        if dsn:
            parsed = urllib.parse.urlparse(dsn)
            host = parsed.hostname or "localhost"
            port = parsed.port or 5432
            db = parsed.path.lstrip("/") or "postgres"
            user = parsed.username or ""
            safe_meta = {
                "host": host,
                "port": port,
                "database": db,
                "user": user,
            }
            return dsn, safe_meta

        host = config.get("host", "").strip() or "localhost"
        port = int(config.get("port") or 5432)
        database = config.get("database", "").strip()
        user = config.get("user", "").strip()
        password = config.get("password", "")
        sslmode = config.get("sslmode", "prefer")

        if not database:
            raise InvalidCredentials("Database name is required.")
        if not user:
            raise InvalidCredentials("Username is required.")

        quoted_user = urllib.parse.quote_plus(user)
        quoted_pass = urllib.parse.quote_plus(password)
        encoded_dsn = f"postgresql://{quoted_user}:{quoted_pass}@{host}:{port}/{database}?sslmode={sslmode}"

        safe_meta = {
            "host": host,
            "port": port,
            "database": database,
            "user": user,
            "sslmode": sslmode,
        }
        return encoded_dsn, safe_meta

    def connect(self, config: dict[str, Any]) -> dict[str, Any]:
        dsn, safe_meta = self._build_dsn(config)
        account_id = f"{safe_meta['user']}@{safe_meta['host']}:{safe_meta['port']}/{safe_meta['database']}"
        display_name = f"PostgreSQL ({safe_meta['database']})"

        return {
            "account_identifier": account_id,
            "display_name": display_name,
            "credentials": {"dsn": dsn},
            "metadata_safe": safe_meta,
            "granted_scopes": ["query_sql"],
        }

    def test_connection(
        self,
        *,
        decrypted_credentials: dict[str, Any],
        metadata_safe: dict[str, Any],
    ) -> dict[str, Any]:
        dsn = decrypted_credentials.get("dsn")
        if not dsn:
            raise InvalidCredentials("Missing PostgreSQL connection string.")

        try:
            import psycopg
            with psycopg.connect(dsn, autocommit=True, connect_timeout=4) as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT version();")
                    row = cur.fetchone()
                    version = row[0] if row else "PostgreSQL (Unknown)"
                    return {"ok": True, "version": version}
        except Exception as exc:
            msg = str(exc).lower()
            if "password authentication failed" in msg:
                raise InvalidCredentials("PostgreSQL password authentication failed.") from exc
            if "connection refused" in msg or "could not connect to server" in msg or "name or service not known" in msg:
                raise Unreachable(f"Could not connect to PostgreSQL server: {exc}") from exc
            if "timeout" in msg:
                raise ConnectionTimeout("Connection to PostgreSQL timed out.") from exc
            if "ssl" in msg or "tls" in msg or "certificate" in msg:
                raise TlsError(f"PostgreSQL SSL/TLS error: {exc}") from exc
            raise ConnectionError(f"PostgreSQL connection failed: {exc}") from exc

    def get_client(
        self,
        *,
        decrypted_credentials: dict[str, Any],
        metadata_safe: dict[str, Any],
    ) -> Any:
        from backend.integrations.database.postgres import PostgreSQLRepository
        from backend.core.config import settings

        dsn = decrypted_credentials.get("dsn")
        if not dsn:
            raise InvalidCredentials("Missing PostgreSQL DSN.")

        return PostgreSQLRepository(
            dsn=dsn,
            pool_min_size=settings.database_pool_min_size,
            pool_max_size=settings.database_pool_max_size,
            timeout_ms=settings.database_statement_timeout_ms,
        )
