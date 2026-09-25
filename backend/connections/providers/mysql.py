"""MySQL & MariaDB connection providers."""
from __future__ import annotations

import logging
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
    Unreachable,
)
from backend.connections.ssrf import validate_db_host

logger = logging.getLogger(__name__)


class MySQLProvider(BaseProvider):
    """Provider for MySQL databases."""

    def __init__(self, provider_id: str = "mysql", name: str = "MySQL", icon: str = "mysql") -> None:
        self._provider_id = provider_id
        self._name = name
        self._icon = icon

    def get_metadata(self) -> ProviderMetadata:
        return ProviderMetadata(
            id=self._provider_id,
            name=self._name,
            categories=("SQL Databases",),
            icon=self._icon,
            description=f"Connect a {self._name} relational database for read-only querying and reporting.",
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
                        "description": f"e.g. mysql://user:password@localhost:3306/enterprise_db",
                    },
                    "host": {
                        "type": "string",
                        "title": "Host",
                        "default": "localhost",
                    },
                    "port": {
                        "type": "integer",
                        "title": "Port",
                        "default": 3306,
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
                },
            },
        )

    def _parse_config(self, config: dict[str, Any]) -> dict[str, Any]:
        dsn = config.get("dsn", "").strip()
        if dsn:
            parsed = urllib.parse.urlparse(dsn)
            host = parsed.hostname or "localhost"
            port = parsed.port or 3306
            db = parsed.path.lstrip("/")
            user = parsed.username or ""
            password = parsed.password or ""
        else:
            host = config.get("host", "").strip() or "localhost"
            port = int(config.get("port") or 3306)
            db = config.get("database", "").strip()
            user = config.get("user", "").strip()
            password = config.get("password", "")

        if not db:
            raise InvalidCredentials("Database name is required.")
        if not user:
            raise InvalidCredentials("Username is required.")

        validate_db_host(host, port)

        return {
            "host": host,
            "port": port,
            "database": db,
            "user": user,
            "password": password,
        }

    def connect(self, config: dict[str, Any]) -> dict[str, Any]:
        parsed = self._parse_config(config)
        account_id = f"{parsed['user']}@{parsed['host']}:{parsed['port']}/{parsed['database']}"
        display_name = f"{self._name} ({parsed['database']})"

        safe_meta = {
            "host": parsed["host"],
            "port": parsed["port"],
            "database": parsed["database"],
            "user": parsed["user"],
        }

        return {
            "account_identifier": account_id,
            "display_name": display_name,
            "credentials": {
                "host": parsed["host"],
                "port": parsed["port"],
                "database": parsed["database"],
                "user": parsed["user"],
                "password": parsed["password"],
            },
            "metadata_safe": safe_meta,
            "granted_scopes": ["query_sql"],
        }

    def test_connection(
        self,
        *,
        decrypted_credentials: dict[str, Any],
        metadata_safe: dict[str, Any],
    ) -> dict[str, Any]:
        host = decrypted_credentials.get("host", "localhost")
        port = int(decrypted_credentials.get("port") or 3306)
        user = decrypted_credentials.get("user", "")
        password = decrypted_credentials.get("password", "")
        database = decrypted_credentials.get("database", "")

        if not user or not database:
            raise InvalidCredentials("Missing MySQL credentials (user or database).")

        try:
            import pymysql
            conn = pymysql.connect(
                host=host,
                port=port,
                user=user,
                password=password,
                database=database,
                connect_timeout=4,
                cursorclass=pymysql.cursors.DictCursor,
            )
            with conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT VERSION() as version;")
                    row = cur.fetchone()
                    version = row["version"] if row else f"{self._name} (Unknown)"
                    return {"ok": True, "version": version}
        except Exception as exc:
            msg = str(exc).lower()
            if "1045" in msg or "access denied" in msg:
                raise InvalidCredentials(f"{self._name} password authentication failed (Access Denied).") from exc
            if "1049" in msg or "unknown database" in msg:
                raise InvalidCredentials(f"Unknown database: {database}") from exc
            if "2003" in msg or "can't connect" in msg or "could not connect" in msg:
                raise Unreachable(f"Could not connect to {self._name} server at {host}:{port}: {exc}") from exc
            if "timed out" in msg:
                raise ConnectionTimeout(f"Connection to {self._name} timed out.") from exc
            raise ConnectionError(f"{self._name} connection error: {exc}") from exc

    def get_client(
        self,
        *,
        decrypted_credentials: dict[str, Any],
        metadata_safe: dict[str, Any],
    ) -> Any:
        import pymysql
        import pymysql.cursors

        class MySQLClient:
            def __init__(self, creds: dict[str, Any]) -> None:
                self._creds = creds

            def query(self, sql: str, params: tuple[Any, ...] | None = None) -> list[dict[str, Any]]:
                conn = pymysql.connect(
                    host=self._creds.get("host", "localhost"),
                    port=int(self._creds.get("port") or 3306),
                    user=self._creds.get("user", ""),
                    password=self._creds.get("password", ""),
                    database=self._creds.get("database", ""),
                    connect_timeout=5,
                    cursorclass=pymysql.cursors.DictCursor,
                )
                with conn:
                    with conn.cursor() as cur:
                        cur.execute(sql, params or ())
                        return cur.fetchall()

        return MySQLClient(decrypted_credentials)


class MariaDBProvider(MySQLProvider):
    """Provider for MariaDB databases (subclassing MySQL with MariaDB defaults)."""

    def __init__(self) -> None:
        super().__init__(provider_id="mariadb", name="MariaDB", icon="mariadb")
