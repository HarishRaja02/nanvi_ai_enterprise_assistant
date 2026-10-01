"""Connection Manager — central orchestrator for connections.

Handles:
- Storage and querying of connections (PostgreSQL with SQLite fallback)
- OAuth state management (PKCE, state tracking, replay prevention)
- Credential encryption/decryption via CredentialEncryptionService
- Authorization enforcement via authz module
- Audit trail via ConnectionAuditWriter
- Scoped client resolution for AI agents
"""
from __future__ import annotations

import json
import logging
import os
import secrets
import sqlite3
import threading
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

from backend.connections.audit import ConnectionAuditWriter, ConnectionEventType
from backend.connections.authz import (
    can_create_org_connection,
    can_create_user_connection,
    can_manage_connection,
    can_use_connection,
    can_view_connection,
)
from backend.connections.base import (
    AmbiguousConnection,
    BaseProvider,
    Capability,
    ConnectionError,
    ConnectionStatus,
    InvalidCredentials,
    OAuthDenied,
    OAuthExpired,
    ProviderUnavailable,
    ReauthRequired,
    ScopeLevel,
)
from backend.connections.encryption import (
    CredentialEncryptionService,
    get_encryption_service,
)
from backend.connections.migration_runner import (
    init_sqlite_connections_schema,
    run_connections_migrations,
)
from backend.connections.registry import ProviderRegistry, get_provider_registry
from backend.connections.schemas import (
    ConnectionPublic,
    CreateConnectionRequest,
    TestConnectionResponse,
    UpdateConnectionRequest,
    ValidateConnectionRequest,
)
from backend.connections.client_resolver import resolve_client_for_agent
from backend.connections.oauth_handler import (
    handle_oauth_callback as _handle_oauth_callback,
    start_oauth as _start_oauth,
)
from backend.core.config import settings
from backend.security.models import UserIdentity

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manages connections, credentials, lifecycle, and agent access."""

    def __init__(
        self,
        encryption_service: CredentialEncryptionService | None = None,
        registry: ProviderRegistry | None = None,
        audit_writer: ConnectionAuditWriter | None = None,
        database_url: str | None = None,
        sqlite_path: str | None = None,
        force_sqlite: bool = False,
    ) -> None:
        self._encryption = encryption_service or get_encryption_service()
        self._registry = registry or get_provider_registry()
        self._force_sqlite = force_sqlite
        if force_sqlite:
            self._database_url = ""
        else:
            self._database_url = database_url if database_url is not None else (settings.supabase_database_url or settings.database_url)
        self._audit = audit_writer or ConnectionAuditWriter(self._database_url)
        self._use_postgres = False
        self._sqlite_path = sqlite_path
        self._sqlite_lock = threading.Lock()
        self._sqlite_conn: sqlite3.Connection | None = None

        self._init_storage()

    def _init_storage(self) -> None:
        """Initialize database backend (PostgreSQL if available, else SQLite)."""
        if not self._force_sqlite and self._database_url:

            try:
                import psycopg
                with psycopg.connect(self._database_url, autocommit=True, connect_timeout=3) as conn:
                    with conn.cursor() as cur:
                        cur.execute("SELECT 1;")
                run_connections_migrations(self._database_url)
                self._use_postgres = True
                logger.info("ConnectionManager initialized with PostgreSQL backend.")
                return
            except Exception as exc:
                logger.warning("Could not connect to PostgreSQL for connections (%s). Falling back to SQLite.", exc)

        # Fallback: SQLite
        self._use_postgres = False
        if not self._sqlite_path:
            import os
            if os.getenv("VERCEL"):
                self._sqlite_path = "/tmp/connections.db"
            else:
                data_dir = Path(__file__).resolve().parent.parent.parent / "data"
                try:
                    data_dir.mkdir(parents=True, exist_ok=True)
                    self._sqlite_path = str(data_dir / "connections.db")
                except Exception:
                    self._sqlite_path = ":memory:"
        self._sqlite_conn = sqlite3.connect(self._sqlite_path, check_same_thread=False)
        self._sqlite_conn.row_factory = sqlite3.Row
        init_sqlite_connections_schema(self._sqlite_conn)
        logger.info("ConnectionManager initialized with SQLite backend (%s).", self._sqlite_path)

    # ── Database Execution Helpers ─────────────────────────────────

    def _execute(self, pg_sql: str, sqlite_sql: str, params: tuple[Any, ...]) -> None:
        if self._use_postgres:
            import psycopg
            with psycopg.connect(self._database_url, autocommit=True, connect_timeout=5) as conn:
                with conn.cursor() as cur:
                    cur.execute(pg_sql, params)
        else:
            with self._sqlite_lock:
                assert self._sqlite_conn is not None
                with self._sqlite_conn:
                    self._sqlite_conn.execute(sqlite_sql, params)

    def _query(self, pg_sql: str, sqlite_sql: str, params: tuple[Any, ...]) -> list[dict[str, Any]]:
        if self._use_postgres:
            import psycopg
            from psycopg.rows import dict_row
            with psycopg.connect(self._database_url, connect_timeout=5, row_factory=dict_row) as conn:
                with conn.cursor() as cur:
                    cur.execute(pg_sql, params)
                    return list(cur.fetchall())
        else:
            with self._sqlite_lock:
                assert self._sqlite_conn is not None
                cur = self._sqlite_conn.execute(sqlite_sql, params)
                rows = cur.fetchall()
                return [dict(row) for row in rows]

    # ── CRUD Operations ───────────────────────────────────────────

    def list_connections(
        self,
        user: UserIdentity,
        *,
        provider: str | None = None,
        category: str | None = None,
        scope: str | None = None,
        status: str | None = None,
        query: str | None = None,
    ) -> list[ConnectionPublic]:
        """List connections visible to the authenticated user."""
        tenant_id = user.tenant_id or "enterprise-tenant"
        pg_sql = """
            SELECT id, tenant_id, owner_user_id, scope_level, provider, display_name,
                   account_identifier, credential_type, granted_scopes, metadata_safe,
                   status, status_reason, last_tested_at, last_used_at, last_synced_at,
                   created_by, created_at, updated_at
            FROM public.connections
            WHERE tenant_id = %s AND deleted_at IS NULL
            ORDER BY created_at DESC;
        """
        sqlite_sql = """
            SELECT id, tenant_id, owner_user_id, scope_level, provider, display_name,
                   account_identifier, credential_type, granted_scopes, metadata_safe,
                   status, status_reason, last_tested_at, last_used_at, last_synced_at,
                   created_by, created_at, updated_at
            FROM connections
            WHERE tenant_id = ? AND deleted_at IS NULL
            ORDER BY created_at DESC;
        """
        rows = self._query(pg_sql, sqlite_sql, (tenant_id,))
        results: list[ConnectionPublic] = []

        for row in rows:
            # Check visibility
            if not can_view_connection(
                user,
                owner_user_id=row.get("owner_user_id"),
                scope_level=row.get("scope_level", "user"),
                connection_tenant_id=row.get("tenant_id", tenant_id),
            ):
                continue

            # Filtering
            if provider and row["provider"] != provider:
                continue
            if scope and row["scope_level"] != scope:
                continue
            if status and row["status"] != status:
                continue
            if query:
                q = query.lower()
                name = (row.get("display_name") or "").lower()
                acc = (row.get("account_identifier") or "").lower()
                prov = (row.get("provider") or "").lower()
                if q not in name and q not in acc and q not in prov:
                    continue

            # Parse metadata_safe and scopes
            meta = row.get("metadata_safe") or {}
            if isinstance(meta, str):
                try:
                    meta = json.loads(meta)
                except Exception:
                    meta = {}

            scopes = row.get("granted_scopes") or []
            if isinstance(scopes, str):
                try:
                    scopes = json.loads(scopes)
                except Exception:
                    scopes = [s.strip() for s in scopes.split(",") if s.strip()]

            results.append(ConnectionPublic(
                id=str(row["id"]),
                provider=row["provider"],
                display_name=row["display_name"],
                account_identifier=row.get("account_identifier"),
                scope_level=row["scope_level"],
                status=row["status"],
                status_reason=row.get("status_reason"),
                granted_scopes=scopes,
                metadata_safe=meta,
                credential_type=row.get("credential_type"),
                last_tested_at=str(row["last_tested_at"]) if row.get("last_tested_at") else None,
                last_used_at=str(row["last_used_at"]) if row.get("last_used_at") else None,
                last_synced_at=str(row["last_synced_at"]) if row.get("last_synced_at") else None,
                created_at=str(row["created_at"]) if row.get("created_at") else None,
                updated_at=str(row["updated_at"]) if row.get("updated_at") else None,
                created_by=row.get("created_by"),
                owner_user_id=row.get("owner_user_id"),
            ))

        return results

    def get_connection(self, connection_id: str, user: UserIdentity) -> ConnectionPublic:
        """Get a single connection safely. Returns 404/ConnectionError if not authorized."""
        row = self._get_raw_connection(connection_id, user)
        meta = row.get("metadata_safe") or {}
        if isinstance(meta, str):
            try:
                meta = json.loads(meta)
            except Exception:
                meta = {}
        scopes = row.get("granted_scopes") or []
        if isinstance(scopes, str):
            try:
                scopes = json.loads(scopes)
            except Exception:
                scopes = [s.strip() for s in scopes.split(",") if s.strip()]

        return ConnectionPublic(
            id=str(row["id"]),
            provider=row["provider"],
            display_name=row["display_name"],
            account_identifier=row.get("account_identifier"),
            scope_level=row["scope_level"],
            status=row["status"],
            status_reason=row.get("status_reason"),
            granted_scopes=scopes,
            metadata_safe=meta,
            credential_type=row.get("credential_type"),
            last_tested_at=str(row["last_tested_at"]) if row.get("last_tested_at") else None,
            last_used_at=str(row["last_used_at"]) if row.get("last_used_at") else None,
            last_synced_at=str(row["last_synced_at"]) if row.get("last_synced_at") else None,
            created_at=str(row["created_at"]) if row.get("created_at") else None,
            updated_at=str(row["updated_at"]) if row.get("updated_at") else None,
            created_by=row.get("created_by"),
            owner_user_id=row.get("owner_user_id"),
        )

    def _get_raw_connection(self, connection_id: str, user: UserIdentity) -> dict[str, Any]:
        """Fetch raw connection record and check view permissions. Throws ConnectionError if denied."""
        tenant_id = user.tenant_id or "enterprise-tenant"
        pg_sql = """
            SELECT * FROM public.connections
            WHERE id = %s AND tenant_id = %s AND deleted_at IS NULL;
        """
        sqlite_sql = """
            SELECT * FROM connections
            WHERE id = ? AND tenant_id = ? AND deleted_at IS NULL;
        """
        rows = self._query(pg_sql, sqlite_sql, (connection_id, tenant_id))
        if not rows:
            # Always return not found (avoid IDOR disclosure)
            raise ConnectionError(f"Connection not found: {connection_id}")

        row = rows[0]
        if not can_view_connection(
            user,
            owner_user_id=row.get("owner_user_id"),
            scope_level=row.get("scope_level", "user"),
            connection_tenant_id=row.get("tenant_id", tenant_id),
        ):
            raise ConnectionError(f"Connection not found: {connection_id}")
        return row

    def create_connection(self, user: UserIdentity, req: CreateConnectionRequest) -> ConnectionPublic:
        """Create a connection via credentials form."""
        tenant_id = user.tenant_id or "enterprise-tenant"
        provider = self._registry.get_provider(req.provider)
        if not provider:
            raise ProviderUnavailable(f"Provider not found: {req.provider}")

        # Permission check
        if req.scope_level == ScopeLevel.ORGANIZATION.value:
            if not can_create_org_connection(user):
                raise ConnectionError("Permission denied: only administrators can create organization connections.")
        else:
            if not can_create_user_connection(user):
                raise ConnectionError("Permission denied: user cannot create connections.")

        # Let provider validate & extract credentials
        connect_data = provider.connect(req.config)
        account_identifier = connect_data.get("account_identifier")
        display_name = req.display_name or connect_data.get("display_name") or provider.get_metadata().name
        raw_credentials = connect_data.get("credentials", {})
        metadata_safe = connect_data.get("metadata_safe", {})
        granted_scopes = connect_data.get("granted_scopes", [])

        # Test before saving if supported
        status = ConnectionStatus.CONNECTED.value
        status_reason = None
        now_iso = datetime.now(timezone.utc).isoformat()
        if Capability.TEST in provider.get_capabilities():
            try:
                provider.test_connection(decrypted_credentials=raw_credentials, metadata_safe=metadata_safe)
            except Exception as exc:
                logger.warning("Test failed during create for %s: %s", req.provider, exc)
                status = ConnectionStatus.ERROR.value
                status_reason = str(exc)

        # Encrypt credentials
        ciphertext, key_id = self._encryption.encrypt_credentials(raw_credentials)

        conn_id = str(uuid.uuid4())
        owner_id = user.subject if req.scope_level == ScopeLevel.USER.value else None
        auth_type = provider.get_metadata().auth_type.value

        pg_sql = """
            INSERT INTO public.connections (
                id, tenant_id, owner_user_id, scope_level, provider, display_name,
                account_identifier, credential_type, encrypted_credentials, encryption_key_id,
                granted_scopes, metadata_safe, status, status_reason, last_tested_at,
                created_by, created_at, updated_at
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s, NOW(), NOW()
            );
        """
        sqlite_sql = """
            INSERT INTO connections (
                id, tenant_id, owner_user_id, scope_level, provider, display_name,
                account_identifier, credential_type, encrypted_credentials, encryption_key_id,
                granted_scopes, metadata_safe, status, status_reason, last_tested_at,
                created_by, created_at, updated_at
            ) VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now')
            );
        """
        self._execute(
            pg_sql,
            sqlite_sql,
            (
                conn_id,
                tenant_id,
                owner_id,
                req.scope_level,
                req.provider,
                display_name,
                account_identifier,
                auth_type,
                ciphertext,
                key_id,
                granted_scopes if self._use_postgres else json.dumps(granted_scopes),
                json.dumps(metadata_safe),
                status,
                status_reason,
                now_iso if status == ConnectionStatus.CONNECTED.value else None,
                user.subject,
            ),
        )

        self._audit.record(
            ConnectionEventType.CREATED,
            tenant_id=tenant_id,
            actor_user_id=user.subject,
            connection_id=conn_id,
            provider=req.provider,
            safe_metadata={"display_name": display_name, "scope_level": req.scope_level},
        )

        return self.get_connection(conn_id, user)

    def update_connection(
        self, connection_id: str, user: UserIdentity, req: UpdateConnectionRequest
    ) -> ConnectionPublic:
        """Update connection settings or display name."""
        row = self._get_raw_connection(connection_id, user)
        if not can_manage_connection(
            user,
            owner_user_id=row.get("owner_user_id"),
            scope_level=row.get("scope_level", "user"),
            connection_tenant_id=row.get("tenant_id", user.tenant_id or "enterprise-tenant"),
        ):
            raise ConnectionError(f"Connection not found: {connection_id}")

        new_name = req.display_name or row["display_name"]
        meta = row.get("metadata_safe") or {}
        if isinstance(meta, str):
            try:
                meta = json.loads(meta)
            except Exception:
                meta = {}
        if req.config:
            meta.update(req.config)

        pg_sql = """
            UPDATE public.connections
            SET display_name = %s, metadata_safe = %s::jsonb, updated_at = NOW()
            WHERE id = %s;
        """
        sqlite_sql = """
            UPDATE connections
            SET display_name = ?, metadata_safe = ?, updated_at = datetime('now')
            WHERE id = ?;
        """
        self._execute(pg_sql, sqlite_sql, (new_name, json.dumps(meta), connection_id))

        self._audit.record(
            ConnectionEventType.UPDATED,
            tenant_id=row["tenant_id"],
            actor_user_id=user.subject,
            connection_id=connection_id,
            provider=row["provider"],
            safe_metadata={"display_name": new_name},
        )

        return self.get_connection(connection_id, user)

    def delete_connection(self, connection_id: str, user: UserIdentity) -> bool:
        """Soft delete connection and revoke at provider if supported."""
        row = self._get_raw_connection(connection_id, user)
        if not can_manage_connection(
            user,
            owner_user_id=row.get("owner_user_id"),
            scope_level=row.get("scope_level", "user"),
            connection_tenant_id=row.get("tenant_id", user.tenant_id or "enterprise-tenant"),
        ):
            raise ConnectionError(f"Connection not found: {connection_id}")

        # Attempt provider disconnect
        provider = self._registry.get_provider(row["provider"])
        if provider and row.get("encrypted_credentials"):
            try:
                creds = self._encryption.decrypt_credentials(row["encrypted_credentials"])
                provider.disconnect(decrypted_credentials=creds)
            except Exception as exc:
                logger.warning("Provider disconnect error for %s: %s", connection_id, exc)

        pg_sql = """
            UPDATE public.connections
            SET deleted_at = NOW(), status = 'DISCONNECTED', updated_at = NOW()
            WHERE id = %s;
        """
        sqlite_sql = """
            UPDATE connections
            SET deleted_at = datetime('now'), status = 'DISCONNECTED', updated_at = datetime('now')
            WHERE id = ?;
        """
        self._execute(pg_sql, sqlite_sql, (connection_id,))

        self._audit.record(
            ConnectionEventType.DISCONNECTED,
            tenant_id=row["tenant_id"],
            actor_user_id=user.subject,
            connection_id=connection_id,
            provider=row["provider"],
        )
        return True

    def test_connection(self, connection_id: str, user: UserIdentity) -> TestConnectionResponse:
        """Test an existing saved connection."""
        row = self._get_raw_connection(connection_id, user)
        if not can_manage_connection(
            user,
            owner_user_id=row.get("owner_user_id"),
            scope_level=row.get("scope_level", "user"),
            connection_tenant_id=row.get("tenant_id", user.tenant_id or "enterprise-tenant"),
        ):
            raise ConnectionError(f"Connection not found: {connection_id}")

        provider = self._registry.get_provider(row["provider"])
        if not provider:
            raise ProviderUnavailable(f"Provider not found: {row['provider']}")

        creds = {}
        if row.get("encrypted_credentials"):
            creds = self._encryption.decrypt_credentials(row["encrypted_credentials"])

        meta = row.get("metadata_safe") or {}
        if isinstance(meta, str):
            try:
                meta = json.loads(meta)
            except Exception:
                meta = {}

        now_iso = datetime.now(timezone.utc).isoformat()
        try:
            res = provider.test_connection(decrypted_credentials=creds, metadata_safe=meta)
            pg_sql = """
                UPDATE public.connections
                SET status = 'CONNECTED', status_reason = NULL, last_tested_at = NOW(), updated_at = NOW()
                WHERE id = %s;
            """
            sqlite_sql = """
                UPDATE connections
                SET status = 'CONNECTED', status_reason = NULL, last_tested_at = datetime('now'), updated_at = datetime('now')
                WHERE id = ?;
            """
            self._execute(pg_sql, sqlite_sql, (connection_id,))
            self._audit.record(
                ConnectionEventType.TESTED,
                tenant_id=row["tenant_id"],
                actor_user_id=user.subject,
                connection_id=connection_id,
                provider=row["provider"],
                safe_metadata={"status": "CONNECTED"},
            )
            return TestConnectionResponse(ok=True, message="Connection test succeeded", details=res)
        except Exception as exc:
            err_msg = getattr(exc, "friendly_message", str(exc))
            pg_sql = """
                UPDATE public.connections
                SET status = 'ERROR', status_reason = %s, last_tested_at = NOW(), updated_at = NOW()
                WHERE id = %s;
            """
            sqlite_sql = """
                UPDATE connections
                SET status = 'ERROR', status_reason = ?, last_tested_at = datetime('now'), updated_at = datetime('now')
                WHERE id = ?;
            """
            self._execute(pg_sql, sqlite_sql, (err_msg, connection_id))
            self._audit.record(
                ConnectionEventType.TESTED,
                tenant_id=row["tenant_id"],
                actor_user_id=user.subject,
                connection_id=connection_id,
                provider=row["provider"],
                safe_metadata={"status": "ERROR", "error": err_msg},
            )
            return TestConnectionResponse(ok=False, message=err_msg)

    def validate_credentials(self, req: ValidateConnectionRequest) -> TestConnectionResponse:
        """Validate credentials before saving."""
        provider = self._registry.get_provider(req.provider)
        if not provider:
            raise ProviderUnavailable(f"Provider not found: {req.provider}")

        try:
            connect_data = provider.connect(req.config)
            raw_credentials = connect_data.get("credentials", {})
            metadata_safe = connect_data.get("metadata_safe", {})

            if Capability.TEST in provider.get_capabilities():
                res = provider.test_connection(decrypted_credentials=raw_credentials, metadata_safe=metadata_safe)
                return TestConnectionResponse(ok=True, message="Credentials are valid.", details=res)
            return TestConnectionResponse(ok=True, message="Configuration is valid.")
        except Exception as exc:
            err_msg = getattr(exc, "friendly_message", str(exc))
            return TestConnectionResponse(ok=False, message=err_msg)

    # ── OAuth Lifecycle ───────────────────────────────────────────

    def start_oauth(
        self,
        provider_id: str,
        user: UserIdentity,
        redirect_uri: str,
        redirect_after: str | None = None,
        scope_level: str = "user",
    ) -> str:
        """Initiate OAuth flow: create signed state and return auth URL."""
        return _start_oauth(
            manager=self,
            provider_id=provider_id,
            user=user,
            redirect_uri=redirect_uri,
            redirect_after=redirect_after,
            scope_level=scope_level,
        )

    def handle_oauth_callback(
        self,
        provider_id: str,
        code: str,
        state: str,
        redirect_uri: str,
        expected_user_id: str | None = None,
        expected_tenant_id: str | None = None,
    ) -> tuple[ConnectionPublic, str | None]:
        """Validate state, consume it, exchange code, store connection."""
        return _handle_oauth_callback(
            manager=self,
            provider_id=provider_id,
            code=code,
            state=state,
            redirect_uri=redirect_uri,
            expected_user_id=expected_user_id,
            expected_tenant_id=expected_tenant_id,
        )

    # ── Agent Client Resolution ────────────────────────────────────

    def get_client_for_agent(
        self,
        provider_or_capability: str,
        user: UserIdentity,
        *,
        connection_id: str | None = None,
    ) -> Any:
        """Resolve an authenticated client for an AI agent."""
        return resolve_client_for_agent(
            manager=self,
            provider_or_capability=provider_or_capability,
            user=user,
            connection_id=connection_id,
        )


# ═══════════════════════════════════════════════════════════════
# Singleton instance
# ═══════════════════════════════════════════════════════════════

_connection_manager: ConnectionManager | None = None


def get_connection_manager() -> ConnectionManager:
    global _connection_manager
    if _connection_manager is None:
        _connection_manager = ConnectionManager()
    return _connection_manager
