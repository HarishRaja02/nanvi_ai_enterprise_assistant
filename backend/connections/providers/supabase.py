"""Supabase Provider (Dual API key + direct PostgreSQL connection)."""
from __future__ import annotations

import logging
import urllib.parse
from typing import Any

import httpx

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
from backend.connections.ssrf import validate_url_ssrf

logger = logging.getLogger(__name__)


class SupabaseProvider(BaseProvider):
    """Supabase provider supporting both REST API and direct Postgres DSN."""

    def __init__(self, http_client: httpx.Client | None = None) -> None:
        self._client = http_client or httpx.Client(timeout=10.0)

    def get_metadata(self) -> ProviderMetadata:
        return ProviderMetadata(
            id="supabase",
            name="Supabase",
            categories=("SQL Databases", "NoSQL / Data Stores", "Cloud"),
            icon="supabase",
            description="Connect your Supabase project (REST API and direct PostgreSQL database).",
            auth_type=AuthType.API_KEY,
            capabilities=frozenset({
                Capability.CREDENTIALS_FORM,
                Capability.TEST,
                Capability.QUERY_SQL,
                Capability.CALL_API,
            }),
            available=True,
            configuration_schema={
                "type": "object",
                "required": ["supabase_url", "supabase_key"],
                "properties": {
                    "supabase_url": {
                        "type": "string",
                        "title": "Project URL",
                        "description": "https://<project-ref>.supabase.co",
                    },
                    "supabase_key": {
                        "type": "string",
                        "title": "API Key (Service Role or Anon Key)",
                        "format": "password",
                    },
                    "database_url": {
                        "type": "string",
                        "title": "Direct Database URL (Optional)",
                        "description": "postgresql://postgres:<password>@db.<ref>.supabase.co:5432/postgres",
                        "format": "password",
                    },
                },
            },
        )

    def connect(self, config: dict[str, Any]) -> dict[str, Any]:
        url = config.get("supabase_url", "").strip().rstrip("/")
        key = config.get("supabase_key", "").strip()
        db_url = config.get("database_url", "").strip()

        if not url:
            raise InvalidCredentials("Supabase project URL is required.")
        if not key:
            raise InvalidCredentials("Supabase API key is required.")

        validate_url_ssrf(url)

        parsed = urllib.parse.urlparse(url)
        project_ref = parsed.netloc.split(".")[0] or parsed.netloc

        return {
            "account_identifier": project_ref,
            "display_name": f"Supabase ({project_ref})",
            "credentials": {
                "supabase_url": url,
                "supabase_key": key,
                "database_url": db_url,
            },
            "metadata_safe": {
                "supabase_url": url,
                "project_ref": project_ref,
                "has_direct_db": bool(db_url),
            },
            "granted_scopes": ["query_sql", "call_api"] if db_url else ["call_api"],
        }

    def test_connection(
        self,
        *,
        decrypted_credentials: dict[str, Any],
        metadata_safe: dict[str, Any],
    ) -> dict[str, Any]:
        url = decrypted_credentials.get("supabase_url", "").strip().rstrip("/")
        key = decrypted_credentials.get("supabase_key", "").strip()
        db_url = decrypted_credentials.get("database_url", "").strip()

        if not url or not key:
            raise InvalidCredentials("Missing Supabase URL or API key.")

        validate_url_ssrf(url)

        headers = {"apikey": key, "Authorization": f"Bearer {key}"}
        api_ok = False
        key_type = "unknown"

        # 1. Test /auth/v1/settings (verifies both publishable/anon and service role keys)
        try:
            auth_resp = self._client.get(f"{url}/auth/v1/settings", headers=headers)
        except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
            raise Unreachable(f"Could not connect to Supabase host: {exc}") from exc
        except httpx.TimeoutException as exc:
            raise ConnectionTimeout("Connection to Supabase timed out.") from exc
        except Exception as exc:
            raise Unreachable(f"Supabase connection error: {exc}") from exc

        if auth_resp.status_code == 200:
            api_ok = True
            key_type = "verified_auth"
        else:
            # 2. Check /rest/v1/ (PostgREST schema / service role check)
            try:
                rest_resp = self._client.get(f"{url}/rest/v1/", headers=headers)
            except Exception as exc:
                raise Unreachable(f"Could not connect to Supabase REST API: {exc}") from exc

            if rest_resp.status_code in {200, 204, 404}:
                api_ok = True
                key_type = "service_role"
            else:
                err_code = rest_resp.headers.get("sb-error-code", "")
                rest_body = rest_resp.text.lower()
                if err_code == "UNAUTHORIZED_INVALID_API_KEY_TYPE" or "secret api key required" in rest_body:
                    api_ok = True
                    key_type = "publishable"
                elif auth_resp.status_code in {401, 403} or rest_resp.status_code in {401, 403}:
                    err_msg = "Supabase API key is invalid or unrecognized."
                    try:
                        auth_json = auth_resp.json()
                        if "message" in auth_json:
                            err_msg = f"Supabase rejected API key: {auth_json['message']}"
                    except Exception:
                        pass
                    raise InvalidCredentials(err_msg)
                else:
                    api_ok = True

        db_ok = None
        if db_url:
            try:
                import psycopg
                with psycopg.connect(db_url, autocommit=True, connect_timeout=4) as conn:
                    with conn.cursor() as cur:
                        cur.execute("SELECT 1;")
                db_ok = True
            except Exception as exc:
                msg = str(exc).lower()
                if "password authentication failed" in msg:
                    raise InvalidCredentials("Direct database password authentication failed.") from exc
                raise ConnectionError(f"Direct Supabase PostgreSQL connection failed: {exc}") from exc

        return {"ok": True, "api_verified": api_ok, "key_type": key_type, "db_verified": db_ok}

    def get_client(
        self,
        *,
        decrypted_credentials: dict[str, Any],
        metadata_safe: dict[str, Any],
    ) -> Any:
        db_url = decrypted_credentials.get("database_url")
        if db_url:
            from backend.integrations.database.postgres import PostgreSQLRepository
            from backend.core.config import settings
            return PostgreSQLRepository(
                dsn=db_url,
                pool_min_size=settings.database_pool_min_size,
                pool_max_size=settings.database_pool_max_size,
                timeout_ms=settings.database_statement_timeout_ms,
            )

        # Fallback to REST client
        class SupabaseRestClient:
            def __init__(self, url: str, key: str, client: httpx.Client) -> None:
                self.url = url
                self.key = key
                self._client = client

            def query_table(self, table: str, limit: int = 50) -> list[dict[str, Any]]:
                headers = {"apikey": self.key, "Authorization": f"Bearer {self.key}"}
                resp = self._client.get(f"{self.url}/rest/v1/{table}?limit={limit}", headers=headers)
                if resp.status_code == 200:
                    return resp.json()
                return []

        return SupabaseRestClient(
            decrypted_credentials.get("supabase_url", ""),
            decrypted_credentials.get("supabase_key", ""),
            self._client,
        )
