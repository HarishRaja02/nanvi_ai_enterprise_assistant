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
    SyncConnectionResponse,
    TestConnectionResponse,
    UpdateConnectionRequest,
    UpdateServiceRequest,
    UpdateSyncConfigRequest,
    ValidateConnectionRequest,
)
from backend.connections.services_catalog import (
    is_service_enabled_for_connection,
    resolve_services_for_connection,
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
        self._use_postgres = False
        self._sqlite_path = sqlite_path
        self._sqlite_lock = threading.Lock()
        self._sqlite_conn: sqlite3.Connection | None = None
        self._pg_pool = None

        self._init_storage()
        self._audit = audit_writer or ConnectionAuditWriter(self._database_url, execute_fn=self._execute)

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
                try:
                    from psycopg_pool import ConnectionPool
                    from psycopg.rows import dict_row
                    self._pg_pool = ConnectionPool(
                        self._database_url,
                        min_size=1,
                        max_size=5,
                        timeout=5,
                        kwargs={"autocommit": True, "row_factory": dict_row},
                        open=True,
                    )
                except Exception as p_err:
                    logger.warning("Could not initialize connection pool for connections (%s); direct fallback.", p_err)
                    self._pg_pool = None
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
            if self._pg_pool:
                try:
                    with self._pg_pool.connection() as conn:
                        with conn.cursor() as cur:
                            cur.execute(pg_sql, params)
                    return
                except Exception as exc:
                    logger.warning("Pooled execute failed (%s); trying direct connect.", exc)
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
            if self._pg_pool:
                try:
                    with self._pg_pool.connection() as conn:
                        with conn.cursor() as cur:
                            cur.execute(pg_sql, params)
                            return list(cur.fetchall())
                except Exception as exc:
                    logger.warning("Pooled query failed (%s); trying direct connect.", exc)
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

    def _row_to_public(self, row: dict[str, Any]) -> ConnectionPublic:
        """Convert a database row into a rich ConnectionPublic object with services."""
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

        sync_cfg = row.get("sync_config") or {}
        if isinstance(sync_cfg, str):
            try:
                sync_cfg = json.loads(sync_cfg)
            except Exception:
                sync_cfg = {"auto_sync": True, "frequency": "1h"}

        services_config_raw = row.get("services_config")
        services = resolve_services_for_connection(
            provider_id=row["provider"],
            services_config_raw=services_config_raw,
            granted_scopes_raw=scopes,
            connection_status=row.get("status", "CONNECTED"),
        )
        enabled_count = sum(1 for s in services if s.enabled)
        scope_lvl = row.get("scope_level", "user")
        account_type = "Organization" if scope_lvl == "organization" else "Personal"

        return ConnectionPublic(
            id=str(row["id"]),
            provider=row["provider"],
            display_name=row["display_name"],
            account_identifier=row.get("account_identifier"),
            scope_level=scope_lvl,
            account_type=account_type,
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
            services=services,
            enabled_services_count=enabled_count,
            total_services_count=len(services),
            auto_sync=bool(sync_cfg.get("auto_sync", True)),
            sync_frequency=sync_cfg.get("frequency", "1h"),
            sync_config=sync_cfg,
        )

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
                   services_config, sync_config, created_by, created_at, updated_at
            FROM public.connections
            WHERE tenant_id = %s AND deleted_at IS NULL
            ORDER BY created_at DESC;
        """
        sqlite_sql = """
            SELECT id, tenant_id, owner_user_id, scope_level, provider, display_name,
                   account_identifier, credential_type, granted_scopes, metadata_safe,
                   status, status_reason, last_tested_at, last_used_at, last_synced_at,
                   services_config, sync_config, created_by, created_at, updated_at
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

            results.append(self._row_to_public(row))

        return results

    def get_connection(self, connection_id: str, user: UserIdentity) -> ConnectionPublic:
        """Get a single connection safely. Returns 404/ConnectionError if not authorized."""
        row = self._get_raw_connection(connection_id, user)
        return self._row_to_public(row)

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

    def update_service(
        self, connection_id: str, service_id: str, user: UserIdentity, req: UpdateServiceRequest
    ) -> ConnectionPublic:
        """Update an individual service's enabled status, permissions, or sync frequency."""
        row = self._get_raw_connection(connection_id, user)
        if not can_manage_connection(
            user,
            owner_user_id=row.get("owner_user_id"),
            scope_level=row.get("scope_level", "user"),
            connection_tenant_id=row.get("tenant_id", user.tenant_id or "enterprise-tenant"),
        ):
            raise ConnectionError("Permission denied: cannot manage this connection's services.")

        services_cfg = row.get("services_config") or {}
        if isinstance(services_cfg, str):
            try:
                services_cfg = json.loads(services_cfg)
            except Exception:
                services_cfg = {}

        current_svc = services_cfg.get(service_id, {})

        if req.enabled is True:
            # Verify required scopes are granted before permitting service activation
            resolved = resolve_services_for_connection(
                row.get("provider", ""),
                services_config_raw=services_cfg,
                granted_scopes_raw=row.get("granted_scopes"),
                connection_status=row.get("status", "CONNECTED"),
            )
            target = next((s for s in resolved if s.id == service_id), None)
            if target and target.status == "UNAUTHORIZED":
                raise ConnectionError(
                    f"Cannot enable service '{target.name}': missing required scopes ({', '.join(target.required_scopes)})."
                )
            current_svc["enabled"] = True
        elif req.enabled is False:
            current_svc["enabled"] = False

        if req.permissions is not None:
            current_svc["permissions"] = req.permissions
        if req.sync_frequency is not None:
            current_svc["sync_frequency"] = req.sync_frequency

        services_cfg[service_id] = current_svc

        pg_sql = """
            UPDATE public.connections
            SET services_config = %s::jsonb, updated_at = NOW()
            WHERE id = %s;
        """
        sqlite_sql = """
            UPDATE connections
            SET services_config = ?, updated_at = datetime('now')
            WHERE id = ?;
        """
        self._execute(pg_sql, sqlite_sql, (json.dumps(services_cfg), connection_id))

        event = ConnectionEventType.SERVICE_ENABLED if req.enabled else ConnectionEventType.SERVICE_DISABLED
        if req.enabled is None and req.permissions is not None:
            event = ConnectionEventType.SERVICE_PERMISSIONS_CHANGED

        self._audit.record(
            event,
            tenant_id=row["tenant_id"],
            actor_user_id=user.subject,
            connection_id=connection_id,
            provider=row["provider"],
            safe_metadata={
                "service_id": service_id,
                "enabled": current_svc.get("enabled"),
                "permissions": current_svc.get("permissions"),
            },
        )

        return self.get_connection(connection_id, user)

    def update_sync_config(
        self, connection_id: str, user: UserIdentity, req: UpdateSyncConfigRequest
    ) -> ConnectionPublic:
        """Update auto-sync and sync frequency settings."""
        row = self._get_raw_connection(connection_id, user)
        if not can_manage_connection(
            user,
            owner_user_id=row.get("owner_user_id"),
            scope_level=row.get("scope_level", "user"),
            connection_tenant_id=row.get("tenant_id", user.tenant_id or "enterprise-tenant"),
        ):
            raise ConnectionError("Permission denied: cannot modify sync settings.")

        sync_cfg = row.get("sync_config") or {}
        if isinstance(sync_cfg, str):
            try:
                sync_cfg = json.loads(sync_cfg)
            except Exception:
                sync_cfg = {"auto_sync": True, "frequency": "1h"}

        if req.auto_sync is not None:
            sync_cfg["auto_sync"] = bool(req.auto_sync)
        freq = req.sync_frequency or getattr(req, "frequency", None)
        if freq is not None:
            sync_cfg["frequency"] = freq

        pg_sql = """
            UPDATE public.connections
            SET sync_config = %s::jsonb, updated_at = NOW()
            WHERE id = %s;
        """
        sqlite_sql = """
            UPDATE connections
            SET sync_config = ?, updated_at = datetime('now')
            WHERE id = ?;
        """
        self._execute(pg_sql, sqlite_sql, (json.dumps(sync_cfg), connection_id))

        self._audit.record(
            ConnectionEventType.UPDATED,
            tenant_id=row["tenant_id"],
            actor_user_id=user.subject,
            connection_id=connection_id,
            provider=row["provider"],
            safe_metadata={"sync_config": sync_cfg},
        )

        return self.get_connection(connection_id, user)

    def sync_connection(self, connection_id: str, user: UserIdentity) -> SyncConnectionResponse:
        """Trigger an on-demand synchronization for all enabled services."""
        row = self._get_raw_connection(connection_id, user)
        if not can_manage_connection(
            user,
            owner_user_id=row.get("owner_user_id"),
            scope_level=row.get("scope_level", "user"),
            connection_tenant_id=row.get("tenant_id", user.tenant_id or "enterprise-tenant"),
        ):
            raise ConnectionError("Permission denied: cannot trigger sync.")

        now_iso = datetime.now(timezone.utc).isoformat()

        # Update last_synced_at in services_config
        services_cfg = row.get("services_config") or {}
        if isinstance(services_cfg, str):
            try:
                services_cfg = json.loads(services_cfg)
            except Exception:
                services_cfg = {}

        conn_public = self._row_to_public(row)
        enabled_svcs = [s.id for s in conn_public.services if s.enabled]
        for sid in enabled_svcs:
            if sid not in services_cfg:
                services_cfg[sid] = {}
            services_cfg[sid]["last_synced_at"] = now_iso

        pg_sql = """
            UPDATE public.connections
            SET last_synced_at = NOW(), services_config = %s::jsonb, updated_at = NOW()
            WHERE id = %s;
        """
        sqlite_sql = """
            UPDATE connections
            SET last_synced_at = datetime('now'), services_config = ?, updated_at = datetime('now')
            WHERE id = ?;
        """
        self._execute(pg_sql, sqlite_sql, (json.dumps(services_cfg), connection_id))

        self._audit.record(
            ConnectionEventType.SYNC_TRIGGERED,
            tenant_id=row["tenant_id"],
            actor_user_id=user.subject,
            connection_id=connection_id,
            provider=row["provider"],
            safe_metadata={"synced_services": enabled_svcs},
        )

        return SyncConnectionResponse(
            ok=True,
            message=f"Synchronized {len(enabled_svcs)} service(s) successfully.",
            synced_services=enabled_svcs,
            synced_at=now_iso,
        )

    def revoke_connection(self, connection_id: str, user: UserIdentity) -> ConnectionPublic:
        """Revoke authorization at provider and mark disconnected."""
        row = self._get_raw_connection(connection_id, user)
        if not can_manage_connection(
            user,
            owner_user_id=row.get("owner_user_id"),
            scope_level=row.get("scope_level", "user"),
            connection_tenant_id=row.get("tenant_id", user.tenant_id or "enterprise-tenant"),
        ):
            raise ConnectionError("Permission denied: cannot revoke this connection.")

        provider = self._registry.get_provider(row["provider"])
        if provider and row.get("encrypted_credentials"):
            try:
                creds = self._encryption.decrypt_credentials(row["encrypted_credentials"])
                provider.disconnect(decrypted_credentials=creds)
            except Exception as exc:
                logger.warning("Provider revocation warning for %s: %s", connection_id, exc)

        pg_sql = """
            UPDATE public.connections
            SET status = 'DISCONNECTED', status_reason = 'Authorization revoked by user',
                encrypted_credentials = NULL, encryption_key_id = NULL,
                updated_at = NOW()
            WHERE id = %s;
        """
        sqlite_sql = """
            UPDATE connections
            SET status = 'DISCONNECTED', status_reason = 'Authorization revoked by user',
                encrypted_credentials = NULL, encryption_key_id = NULL,
                updated_at = datetime('now')
            WHERE id = ?;
        """
        self._execute(pg_sql, sqlite_sql, (connection_id,))

        self._audit.record(
            ConnectionEventType.AUTHORIZATION_REVOKED,
            tenant_id=row["tenant_id"],
            actor_user_id=user.subject,
            connection_id=connection_id,
            provider=row["provider"],
        )

        return self.get_connection(connection_id, user)

    def list_connection_audit(self, connection_id: str, user: UserIdentity) -> list[dict[str, Any]]:
        """List audit events specifically for this connection."""
        row = self._get_raw_connection(connection_id, user)
        tenant_id = user.tenant_id or "enterprise-tenant"
        pg_sql = """
            SELECT id, tenant_id, actor_user_id, connection_id, provider, event, safe_metadata, ip, created_at
            FROM public.connection_audit_events
            WHERE connection_id = %s AND tenant_id = %s
            ORDER BY created_at DESC LIMIT 50;
        """
        sqlite_sql = """
            SELECT id, tenant_id, actor_user_id, connection_id, provider, event, safe_metadata, ip, created_at
            FROM connection_audit_events
            WHERE connection_id = ? AND tenant_id = ?
            ORDER BY created_at DESC LIMIT 50;
        """
        raw_events = self._query(pg_sql, sqlite_sql, (connection_id, tenant_id))
        for evt in raw_events:
            if "event" in evt and "event_type" not in evt:
                evt["event_type"] = evt["event"]
        return raw_events

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
