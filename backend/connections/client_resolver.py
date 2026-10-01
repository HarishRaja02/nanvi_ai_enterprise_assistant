"""Client resolver for AI agents interacting with connected enterprise providers."""
from __future__ import annotations

import json
from typing import Any

from backend.connections.audit import ConnectionEventType
from backend.connections.authz import can_use_connection
from backend.connections.base import AmbiguousConnection, Capability, ProviderUnavailable
from backend.security.models import UserIdentity


def resolve_client_for_agent(
    manager: Any,
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
        row = manager._get_raw_connection(connection_id, user)
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
        candidates = manager._query(pg_sql, sqlite_sql, (tenant_id, user.subject))

        matching: list[dict[str, Any]] = []
        for c in candidates:
            if not can_use_connection(
                user,
                owner_user_id=c.get("owner_user_id"),
                scope_level=c.get("scope_level", "user"),
                connection_tenant_id=c.get("tenant_id", tenant_id),
            ):
                continue

            p = manager._registry.get_provider(c["provider"])
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

    provider = manager._registry.get_provider(row["provider"])
    if not provider:
        raise ProviderUnavailable(f"Provider not found: {row['provider']}")

    creds = {}
    if row.get("encrypted_credentials"):
        creds = manager._encryption.decrypt_credentials(row["encrypted_credentials"])

    if Capability.REFRESH in provider.get_capabilities():
        new_creds = provider.refresh_credentials(decrypted_credentials=creds)
        if new_creds:
            creds = new_creds
            new_cipher, key_id = manager._encryption.encrypt_credentials(new_creds)
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
            manager._execute(pg_ref, sqlite_ref, (new_cipher, key_id, row["id"]))

    pg_used = "UPDATE public.connections SET last_used_at = NOW() WHERE id = %s;"
    sqlite_used = "UPDATE connections SET last_used_at = datetime('now') WHERE id = ?;"
    manager._execute(pg_used, sqlite_used, (row["id"],))

    manager._audit.record(
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
