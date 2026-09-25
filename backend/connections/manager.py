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
        provider = self._registry.get_provider(provider_id)
        if not provider:
            raise ProviderUnavailable(f"Provider not found: {provider_id}")

        if Capability.OAUTH not in provider.get_capabilities():
            raise ConnectionError(f"Provider '{provider_id}' does not support OAuth.")

        if scope_level == ScopeLevel.ORGANIZATION.value and not can_create_org_connection(user):
            raise ConnectionError("Permission denied: only administrators can create organization connections.")

        state = secrets.token_urlsafe(32)
        pkce_verifier = secrets.token_urlsafe(64)
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)
        tenant_id = user.tenant_id or "enterprise-tenant"

        pg_sql = """
            INSERT INTO public.oauth_states (
                state, user_id, tenant_id, provider, pkce_verifier, redirect_after, expires_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s);
        """
        sqlite_sql = """
            INSERT INTO oauth_states (
                state, user_id, tenant_id, provider, pkce_verifier, redirect_after, expires_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?);
        """
        self._execute(
            pg_sql,
            sqlite_sql,
            (
                state,
                user.subject,
                tenant_id,
                provider_id,
                pkce_verifier,
                f"{redirect_after}|scope:{scope_level}" if redirect_after else f"scope:{scope_level}",
                expires_at.isoformat(),
            ),
        )

        auth_url = provider.get_authorization_url(
            user_id=user.subject,
            tenant_id=tenant_id,
            redirect_uri=redirect_uri,
            state=state,
            pkce_verifier=pkce_verifier,
        )
        return auth_url

    def handle_oauth_callback(
        self,
        provider_id: str,
        code: str,
        state: str,
        redirect_uri: str,
    ) -> tuple[ConnectionPublic, str | None]:
        """Validate state, consume it, exchange code, store connection.

        Returns (connection_public, redirect_after).
        """
        # Validate state
        pg_sql = "SELECT * FROM public.oauth_states WHERE state = %s;"
        sqlite_sql = "SELECT * FROM oauth_states WHERE state = ?;"
        rows = self._query(pg_sql, sqlite_sql, (state,))
        if not rows:
            raise OAuthDenied("Invalid or expired OAuth state.")

        state_row = rows[0]
        if state_row.get("consumed_at"):
            raise OAuthDenied("OAuth state has already been consumed (replay attack prevention).")

        expires_val = state_row.get("expires_at")
        if isinstance(expires_val, str):
            exp = datetime.fromisoformat(expires_val.replace("Z", "+00:00"))
        else:
            exp = expires_val
        if exp < datetime.now(timezone.utc):
            raise OAuthExpired("OAuth state has expired. Please restart authorization.")

        # Mark consumed
        pg_consume = "UPDATE public.oauth_states SET consumed_at = NOW() WHERE state = %s;"
        sqlite_consume = "UPDATE oauth_states SET consumed_at = datetime('now') WHERE state = ?;"
        self._execute(pg_consume, sqlite_consume, (state,))

        provider = self._registry.get_provider(provider_id)
        if not provider:
            raise ProviderUnavailable(f"Provider not found: {provider_id}")

        pkce_verifier = state_row.get("pkce_verifier")
        auth_data = provider.handle_callback(
            code=code,
            state=state,
            redirect_uri=redirect_uri,
            pkce_verifier=pkce_verifier,
        )

        user_id = state_row["user_id"]
        tenant_id = state_row["tenant_id"]

        redirect_raw = state_row.get("redirect_after") or ""
        scope_level = "user"
        redirect_after = None
        if "|scope:" in redirect_raw:
            parts = redirect_raw.split("|scope:")
            redirect_after = parts[0] if parts[0] else None
            scope_level = parts[1]
        elif redirect_raw.startswith("scope:"):
            scope_level = redirect_raw.replace("scope:", "")
        elif redirect_raw:
            redirect_after = redirect_raw

        account_identifier = auth_data.get("account_identifier")
        display_name = auth_data.get("display_name") or f"{provider.get_metadata().name} ({account_identifier or user_id})"
        raw_credentials = auth_data.get("credentials", {})
        metadata_safe = auth_data.get("metadata_safe", {})
        granted_scopes = auth_data.get("granted_scopes", [])

        # Encrypt
        ciphertext, key_id = self._encryption.encrypt_credentials(raw_credentials)
        now_iso = datetime.now(timezone.utc).isoformat()
        owner_id = user_id if scope_level == ScopeLevel.USER.value else None

        # Check if an existing connection exists for this user/tenant/provider/account_identifier
        pg_check = """
            SELECT id FROM public.connections
            WHERE tenant_id = %s AND provider = %s AND scope_level = %s
              AND COALESCE(owner_user_id, '') = COALESCE(%s, '')
              AND COALESCE(account_identifier, '') = COALESCE(%s, '')
              AND deleted_at IS NULL;
        """
        sqlite_check = """
            SELECT id FROM connections
            WHERE tenant_id = ? AND provider = ? AND scope_level = ?
              AND IFNULL(owner_user_id, '') = IFNULL(?, '')
              AND IFNULL(account_identifier, '') = IFNULL(?, '')
              AND deleted_at IS NULL;
        """
        existing = self._query(pg_check, sqlite_check, (tenant_id, provider_id, scope_level, owner_id, account_identifier))

        if existing:
            conn_id = str(existing[0]["id"])
            pg_update = """
                UPDATE public.connections
                SET encrypted_credentials = %s, encryption_key_id = %s,
                    granted_scopes = %s, metadata_safe = %s::jsonb,
                    status = 'CONNECTED', status_reason = NULL,
                    last_synced_at = NOW(), updated_at = NOW()
                WHERE id = %s;
            """
            sqlite_update = """
                UPDATE connections
                SET encrypted_credentials = ?, encryption_key_id = ?,
                    granted_scopes = ?, metadata_safe = ?,
                    status = 'CONNECTED', status_reason = NULL,
                    last_synced_at = datetime('now'), updated_at = datetime('now')
                WHERE id = ?;
            """
            self._execute(
                pg_update,
                sqlite_update,
                (
                    ciphertext,
                    key_id,
                    granted_scopes if self._use_postgres else json.dumps(granted_scopes),
                    json.dumps(metadata_safe),
                    conn_id,
                ),
            )
            self._audit.record(
                ConnectionEventType.OAUTH_REAUTHORIZED,
                tenant_id=tenant_id,
                actor_user_id=user_id,
                connection_id=conn_id,
                provider=provider_id,
                safe_metadata={"account_identifier": account_identifier},
            )
        else:
            conn_id = str(uuid.uuid4())
            pg_ins = """
                INSERT INTO public.connections (
                    id, tenant_id, owner_user_id, scope_level, provider, display_name,
                    account_identifier, credential_type, encrypted_credentials, encryption_key_id,
                    granted_scopes, metadata_safe, status, status_reason, last_synced_at,
                    created_by, created_at, updated_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, 'oauth2', %s, %s, %s, %s::jsonb, 'CONNECTED', NULL, NOW(), %s, NOW(), NOW()
                );
            """
            sqlite_ins = """
                INSERT INTO connections (
                    id, tenant_id, owner_user_id, scope_level, provider, display_name,
                    account_identifier, credential_type, encrypted_credentials, encryption_key_id,
                    granted_scopes, metadata_safe, status, status_reason, last_synced_at,
                    created_by, created_at, updated_at
                ) VALUES (
                    ?, ?, ?, ?, ?, ?, ?, 'oauth2', ?, ?, ?, ?, 'CONNECTED', NULL, datetime('now'), ?, datetime('now'), datetime('now')
                );
            """
            self._execute(
                pg_ins,
                sqlite_ins,
                (
                    conn_id,
                    tenant_id,
                    owner_id,
                    scope_level,
                    provider_id,
                    display_name,
                    account_identifier,
                    ciphertext,
                    key_id,
                    granted_scopes if self._use_postgres else json.dumps(granted_scopes),
                    json.dumps(metadata_safe),
                    user_id,
                ),
            )
            self._audit.record(
                ConnectionEventType.OAUTH_CONNECTED,
                tenant_id=tenant_id,
                actor_user_id=user_id,
                connection_id=conn_id,
                provider=provider_id,
                safe_metadata={"account_identifier": account_identifier},
            )

        # Build mock user identity for fetching
        from backend.security.authorization.rbac import Role
        mock_user = UserIdentity(
            subject=user_id,
            issuer="internal",
            email=account_identifier or "",
            name="",
            tenant_id=tenant_id,
            department="Operations",
            roles=frozenset({Role.EMPLOYEE, Role.IT_ADMIN}),
        )
        return self.get_connection(conn_id, mock_user), redirect_after

    # ── Agent Client Resolution ────────────────────────────────────

    def get_client_for_agent(
        self,
        provider_or_capability: str,
        user: UserIdentity,
        *,
        connection_id: str | None = None,
    ) -> Any:
        """Resolve an authenticated client for an AI agent.

        Agents never receive raw credentials. Returns ready-to-use client object.
        """
        tenant_id = user.tenant_id or "enterprise-tenant"

        if connection_id:
            row = self._get_raw_connection(connection_id, user)
        else:
            # Query candidate connections
            pg_sql = """
                SELECT * FROM public.connections
                WHERE tenant_id = %s AND deleted_at IS NULL AND status = 'CONNECTED'
                ORDER BY (scope_level = 'user' AND owner_user_id = %s) DESC, created_at DESC;
            """
            sqlite_sql = """
                SELECT * FROM connections
                WHERE tenant_id = ? AND deleted_at IS NULL AND status = 'CONNECTED'
                ORDER BY (scope_level = 'user' AND owner_user_id = ?) DESC, created_at DESC;
            """
            candidates = self._query(pg_sql, sqlite_sql, (tenant_id, user.subject))

            matching: list[dict[str, Any]] = []
            for c in candidates:
                if not can_use_connection(
                    user,
                    owner_user_id=c.get("owner_user_id"),
                    scope_level=c.get("scope_level", "user"),
                    connection_tenant_id=c.get("tenant_id", tenant_id),
                ):
                    continue

                p = self._registry.get_provider(c["provider"])
                if not p:
                    continue

                if c["provider"] == provider_or_capability:
                    matching.append(c)
                elif any(cap.value == provider_or_capability for cap in p.get_capabilities()):
                    matching.append(c)

            if not matching:
                raise ProviderUnavailable(
                    f"No active connection found for '{provider_or_capability}'. Please connect it in Settings -> Connections."
                )

            # If user has a personal connection, prefer it over org
            personal = [m for m in matching if m.get("scope_level") == "user" and m.get("owner_user_id") == user.subject]
            if len(personal) == 1:
                row = personal[0]
            elif len(personal) > 1:
                raise AmbiguousConnection(
                    f"Multiple personal connections found for '{provider_or_capability}'. Please specify connection_id."
                )
            elif len(matching) == 1:
                row = matching[0]
            else:
                raise AmbiguousConnection(
                    f"Multiple connections found for '{provider_or_capability}'. Please specify connection_id."
                )

        provider = self._registry.get_provider(row["provider"])
        if not provider:
            raise ProviderUnavailable(f"Provider not found: {row['provider']}")

        creds = {}
        if row.get("encrypted_credentials"):
            creds = self._encryption.decrypt_credentials(row["encrypted_credentials"])

        # Check if refresh needed
        if Capability.REFRESH in provider.get_capabilities():
            new_creds = provider.refresh_credentials(decrypted_credentials=creds)
            if new_creds:
                creds = new_creds
                new_cipher, key_id = self._encryption.encrypt_credentials(new_creds)
                pg_ref = """
                    UPDATE public.connections
                    SET encrypted_credentials = %s, encryption_key_id = %s, updated_at = NOW()
                    WHERE id = %s;
                """
                sqlite_ref = """
                    UPDATE connections
                    SET encrypted_credentials = ?, encryption_key_id = ?, updated_at = datetime('now')
                    WHERE id = ?;
                """
                self._execute(pg_ref, sqlite_ref, (new_cipher, key_id, row["id"]))

        # Update last_used_at
        pg_used = "UPDATE public.connections SET last_used_at = NOW() WHERE id = %s;"
        sqlite_used = "UPDATE connections SET last_used_at = datetime('now') WHERE id = ?;"
        self._execute(pg_used, sqlite_used, (row["id"],))

        self._audit.record(
            ConnectionEventType.USED_BY_AGENT,
            tenant_id=row["tenant_id"],
            actor_user_id=user.subject,
            connection_id=str(row["id"]),
            provider=row["provider"],
        )

        meta = row.get("metadata_safe") or {}
        if isinstance(meta, str):
            try:
                meta = json.loads(meta)
            except Exception:
                meta = {}

        return provider.get_client(decrypted_credentials=creds, metadata_safe=meta)


# ═══════════════════════════════════════════════════════════════
# Singleton instance
# ═══════════════════════════════════════════════════════════════

_connection_manager: ConnectionManager | None = None


def get_connection_manager() -> ConnectionManager:
    global _connection_manager
    if _connection_manager is None:
        _connection_manager = ConnectionManager()
    return _connection_manager
