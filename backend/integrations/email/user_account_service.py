"""User Email Account Service for multi-tenant and per-user email authorization.

Stores and manages individual user mailbox connections (e.g. Google Gmail OAuth 2.0
refresh tokens, access tokens, and mailbox metadata) per enterprise user.
Supports Supabase Cloud / PostgreSQL with resilient fallback to encrypted local store.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.core.config import settings

logger = logging.getLogger(__name__)

STORAGE_PATH = Path("backend/storage/user_email_accounts.json")


@dataclass
class UserEmailAccount:
    id: str
    user_id: str
    email_address: str
    display_name: str = ""
    provider: str = "google"
    access_token: str = ""
    refresh_token: str = ""
    token_expires_at: float = 0.0
    scopes: str = "gmail.readonly,email,profile"
    avatar_url: str | None = None
    tenant_id: str = "enterprise-tenant"
    is_active: bool = True
    connected_at: str = ""
    last_synced_at: str | None = None

    def is_token_expired(self) -> bool:
        """Returns True if the access token is within 60 seconds of expiring."""
        return time.time() >= (self.token_expires_at - 60)


class UserEmailAccountService:
    """Manages connected email mailboxes per enterprise user."""

    def __init__(self, storage_path: Path | None = None) -> None:
        self._path = storage_path or STORAGE_PATH
        self._lock = threading.Lock()
        self._ensure_storage()
        self._init_db_schema()

    def _ensure_storage(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        if not self._path.exists():
            with open(self._path, "w", encoding="utf-8") as f:
                json.dump([], f)

    def _init_db_schema(self) -> None:
        """Ensure public.user_email_accounts exists in target database."""
        target_dsn = settings.supabase_database_url or settings.database_url
        if not target_dsn:
            return
        try:
            import psycopg
            with psycopg.connect(target_dsn, autocommit=True, connect_timeout=3) as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        CREATE TABLE IF NOT EXISTS public.user_email_accounts (
                            id VARCHAR(120) PRIMARY KEY,
                            user_id VARCHAR(120) NOT NULL,
                            tenant_id VARCHAR(120) NOT NULL DEFAULT 'enterprise-tenant',
                            email_address VARCHAR(255) NOT NULL,
                            display_name VARCHAR(255),
                            provider VARCHAR(50) NOT NULL DEFAULT 'google',
                            access_token TEXT,
                            refresh_token TEXT,
                            token_expires_at DOUBLE PRECISION,
                            scopes TEXT,
                            avatar_url TEXT,
                            is_active BOOLEAN NOT NULL DEFAULT TRUE,
                            connected_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                            last_synced_at TIMESTAMP WITH TIME ZONE
                        );
                        CREATE INDEX IF NOT EXISTS idx_user_email_user ON public.user_email_accounts(user_id);
                    """)
            logger.info("Initialized public.user_email_accounts table in database")
        except Exception as exc:
            logger.warning("Could not initialize DB schema for user_email_accounts (using local storage fallback): %s", exc)

    def _read_local_accounts(self) -> list[dict[str, Any]]:
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []

    def _write_local_accounts(self, accounts: list[dict[str, Any]]) -> None:
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(accounts, f, indent=2)

    def get_accounts(self, user_id: str) -> list[UserEmailAccount]:
        """Fetch all connected email accounts for a specific user."""
        target_dsn = settings.supabase_database_url or settings.database_url
        if target_dsn:
            try:
                import psycopg
                with psycopg.connect(target_dsn, connect_timeout=3) as conn:
                    with conn.cursor() as cur:
                        cur.execute("""
                            SELECT id, user_id, tenant_id, email_address, display_name, provider,
                                   access_token, refresh_token, token_expires_at, scopes, avatar_url,
                                   is_active, connected_at, last_synced_at
                            FROM public.user_email_accounts
                            WHERE user_id = %s AND is_active = TRUE
                            ORDER BY connected_at DESC
                        """, (user_id,))
                        rows = cur.fetchall()
                        if rows:
                            return [
                                UserEmailAccount(
                                    id=r[0],
                                    user_id=r[1],
                                    tenant_id=r[2] or "enterprise-tenant",
                                    email_address=r[3],
                                    display_name=r[4] or "",
                                    provider=r[5] or "google",
                                    access_token=r[6] or "",
                                    refresh_token=r[7] or "",
                                    token_expires_at=float(r[8] or 0.0),
                                    scopes=r[9] or "",
                                    avatar_url=r[10],
                                    is_active=bool(r[11]),
                                    connected_at=str(r[12] or ""),
                                    last_synced_at=str(r[13]) if r[13] else None,
                                )
                                for r in rows
                            ]
            except Exception as exc:
                logger.debug("Database fetch failed, checking local store: %s", exc)

        with self._lock:
            data = self._read_local_accounts()
            matching = [
                UserEmailAccount(**d) for d in data
                if d.get("user_id") == user_id and d.get("is_active", True)
            ]
            return matching

    def get_active_account(self, user_id: str) -> UserEmailAccount | None:
        """Get the primary active connected mailbox for the given user."""
        accounts = self.get_accounts(user_id)
        if accounts:
            return accounts[0]
        return None

    def save_account(self, account: UserEmailAccount) -> UserEmailAccount:
        """Upsert a connected email account in the database and local replica."""
        if not account.id:
            account.id = str(uuid.uuid4())
        if not account.connected_at:
            account.connected_at = datetime.now(timezone.utc).isoformat()

        # 1. Update Database if available
        target_dsn = settings.supabase_database_url or settings.database_url
        if target_dsn:
            try:
                import psycopg
                with psycopg.connect(target_dsn, autocommit=True, connect_timeout=3) as conn:
                    with conn.cursor() as cur:
                        cur.execute("""
                            INSERT INTO public.user_email_accounts (
                                id, user_id, tenant_id, email_address, display_name, provider,
                                access_token, refresh_token, token_expires_at, scopes, avatar_url,
                                is_active, connected_at, last_synced_at
                            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW())
                            ON CONFLICT (id) DO UPDATE SET
                                email_address = EXCLUDED.email_address,
                                display_name = EXCLUDED.display_name,
                                provider = EXCLUDED.provider,
                                access_token = EXCLUDED.access_token,
                                refresh_token = EXCLUDED.refresh_token,
                                token_expires_at = EXCLUDED.token_expires_at,
                                scopes = EXCLUDED.scopes,
                                avatar_url = EXCLUDED.avatar_url,
                                is_active = EXCLUDED.is_active,
                                last_synced_at = NOW();
                        """, (
                            account.id, account.user_id, account.tenant_id, account.email_address,
                            account.display_name, account.provider, account.access_token,
                            account.refresh_token, account.token_expires_at, account.scopes,
                            account.avatar_url, account.is_active,
                        ))
            except Exception as exc:
                logger.warning("Could not persist email account to DB: %s", exc)

        # 2. Update local JSON replica
        with self._lock:
            accounts = self._read_local_accounts()
            updated = False
            for i, acc in enumerate(accounts):
                if acc.get("id") == account.id or (
                    acc.get("user_id") == account.user_id and acc.get("email_address") == account.email_address
                ):
                    accounts[i] = asdict(account)
                    updated = True
                    break
            if not updated:
                accounts.append(asdict(account))
            self._write_local_accounts(accounts)

        return account

    def update_tokens(self, account_id: str, access_token: str, expires_in: int) -> None:
        """Update access token and expiry time for an account."""
        expires_at = time.time() + expires_in
        target_dsn = settings.supabase_database_url or settings.database_url
        if target_dsn:
            try:
                import psycopg
                with psycopg.connect(target_dsn, autocommit=True, connect_timeout=3) as conn:
                    with conn.cursor() as cur:
                        cur.execute("""
                            UPDATE public.user_email_accounts
                            SET access_token = %s, token_expires_at = %s, last_synced_at = NOW()
                            WHERE id = %s
                        """, (access_token, expires_at, account_id))
            except Exception as exc:
                logger.warning("Could not update token in DB: %s", exc)

        with self._lock:
            accounts = self._read_local_accounts()
            for acc in accounts:
                if acc.get("id") == account_id:
                    acc["access_token"] = access_token
                    acc["token_expires_at"] = expires_at
                    acc["last_synced_at"] = datetime.now(timezone.utc).isoformat()
                    break
            self._write_local_accounts(accounts)

    def disconnect_account(self, user_id: str, account_id: str | None = None) -> bool:
        """Disconnect/deactivate an email account for a user."""
        target_dsn = settings.supabase_database_url or settings.database_url
        if target_dsn:
            try:
                import psycopg
                with psycopg.connect(target_dsn, autocommit=True, connect_timeout=3) as conn:
                    with conn.cursor() as cur:
                        if account_id:
                            cur.execute("""
                                UPDATE public.user_email_accounts
                                SET is_active = FALSE
                                WHERE user_id = %s AND id = %s
                            """, (user_id, account_id))
                        else:
                            cur.execute("""
                                UPDATE public.user_email_accounts
                                SET is_active = FALSE
                                WHERE user_id = %s
                            """, (user_id,))
            except Exception as exc:
                logger.warning("Could not disconnect account in DB: %s", exc)

        with self._lock:
            accounts = self._read_local_accounts()
            for acc in accounts:
                if acc.get("user_id") == user_id:
                    if account_id is None or acc.get("id") == account_id:
                        acc["is_active"] = False
            self._write_local_accounts(accounts)

        return True


# Global singleton instance
_account_service: UserEmailAccountService | None = None


def get_user_email_account_service() -> UserEmailAccountService:
    global _account_service
    if _account_service is None:
        _account_service = UserEmailAccountService()
    return _account_service
