from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import sqlite3
import threading
import uuid
from pathlib import Path
from typing import Any

from backend.core.config import settings
from backend.security.authorization.rbac import Role

PASSWORD_SCRYPT_N = 1 << 14
PASSWORD_SCRYPT_R = 8
PASSWORD_SCRYPT_P = 1
PASSWORD_KEY_LENGTH = 32
PASSWORD_MIN_LENGTH = 12

DEMO_ACCOUNTS = (
    ("ceo", "ceo@nanvi", "Superior", "Arjun Mehta", "Executive", "ceo@nanvi.local"),
    ("finance", "finance@nanvi", "Supervisor", "Priya Sharma", "Finance", "finance@nanvi.local"),
    ("manager", "manager@nanvi", "Supervisor", "Rahul Patel", "Operations", "manager@nanvi.local"),
    ("engineer", "engineer@nanvi", "Project Engineer", "Maya Nair", "Engineering", "engineer@nanvi.local"),
    ("hr", "hr@nanvi", "Project Engineer", "Kavita Reddy", "Human Resources", "hr@nanvi.local"),
    ("employee", "employee@nanvi", "Employee", "Ankit Singh", "Operations", "employee@nanvi.local"),
)


def hash_password(password: str, salt: bytes | None = None) -> tuple[str, str]:
    if len(password) < PASSWORD_MIN_LENGTH:
        raise ValueError(f"Password must be at least {PASSWORD_MIN_LENGTH} characters long.")
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=PASSWORD_SCRYPT_N,
        r=PASSWORD_SCRYPT_R,
        p=PASSWORD_SCRYPT_P,
        dklen=PASSWORD_KEY_LENGTH,
        maxmem=64 * 1024 * 1024,
    )
    return salt.hex(), digest.hex()


def verify_password(password: str, salt_hex: str, digest_hex: str) -> bool:
    try:
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(digest_hex)
        actual = hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=PASSWORD_SCRYPT_N,
            r=PASSWORD_SCRYPT_R,
            p=PASSWORD_SCRYPT_P,
            dklen=PASSWORD_KEY_LENGTH,
            maxmem=64 * 1024 * 1024,
        )
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


class LocalAccountStore:
    def __init__(self, dsn: str = "", sqlite_path: str | Path | None = None) -> None:
        self._dsn = dsn
        self._sqlite_path = Path(sqlite_path) if sqlite_path else Path(__file__).resolve().parents[1] / "storage" / "local_accounts.sqlite3"
        self._initialize_lock = threading.Lock()
        self._initialized = False
        self._pool = None
        if self._dsn:
            try:
                from psycopg_pool import ConnectionPool
                from psycopg.rows import dict_row
                min_size = max(1, settings.database_pool_min_size)
                max_size = max(5, settings.database_pool_max_size)
                self._pool = ConnectionPool(
                    conninfo=self._dsn,
                    min_size=min_size,
                    max_size=max_size,
                    kwargs={"row_factory": dict_row, "connect_timeout": 5},
                    open=True,
                )
                import atexit
                atexit.register(self.close)
            except Exception:
                self._pool = None

    def close(self) -> None:
        if self._pool is not None:
            try:
                self._pool.close(timeout=1.0)
            except Exception:
                pass

    @property
    def _table(self) -> str:
        return "public.nanvi_local_accounts" if self._dsn else "local_accounts"

    def _connect(self):
        if self._dsn:
            from backend.core.exceptions import DependencyUnavailableError
            try:
                if self._pool is not None:
                    return self._pool.connection(timeout=3)
                import psycopg
                from psycopg.rows import dict_row
                return psycopg.connect(self._dsn, row_factory=dict_row, connect_timeout=3)
            except Exception as exc:
                if settings.is_production:
                    sanitized_host = self._dsn.split("@")[-1] if "@" in self._dsn else "configured host"
                    raise DependencyUnavailableError(
                        f"PostgreSQL database connection failed for '{sanitized_host}': {exc}. "
                        "In cloud deployment (Vercel/AWS/Azure), make sure SUPABASE_DATABASE_URL is set to your cloud PostgreSQL URI, not localhost.",
                        dependency="database",
                    ) from exc
                import logging
                logging.getLogger(__name__).warning("Could not connect to PostgreSQL/Supabase (%s). Using local SQLite fallback.", exc)
                self._dsn = ""
                if self._pool is not None:
                    try:
                        self._pool.close(timeout=0.5)
                    except Exception:
                        pass
                    self._pool = None

        self._sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self._sqlite_path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        return connection

    def initialize(self) -> None:
        with self._initialize_lock:
            if self._initialized:
                return
            with self._connect() as connection:
                if self._dsn:
                    connection.execute(
                        """
                        CREATE TABLE IF NOT EXISTS public.nanvi_local_accounts (
                            id TEXT PRIMARY KEY,
                            tenant_id TEXT NOT NULL,
                            username TEXT NOT NULL,
                            password_salt TEXT NOT NULL,
                            password_hash TEXT NOT NULL,
                            role TEXT NOT NULL,
                            display_name TEXT NOT NULL,
                            email TEXT,
                            department TEXT,
                            active BOOLEAN NOT NULL DEFAULT TRUE,
                            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                            UNIQUE (tenant_id, username)
                        )
                        """
                    )
                    connection.commit()
                else:
                    connection.execute(
                        """
                        CREATE TABLE IF NOT EXISTS local_accounts (
                            id TEXT PRIMARY KEY,
                            tenant_id TEXT NOT NULL,
                            username TEXT NOT NULL,
                            password_salt TEXT NOT NULL,
                            password_hash TEXT NOT NULL,
                            role TEXT NOT NULL,
                            display_name TEXT NOT NULL,
                            email TEXT,
                            department TEXT,
                            active INTEGER NOT NULL DEFAULT 1,
                            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                            UNIQUE (tenant_id, username)
                        )
                        """
                    )
                    connection.commit()
                count = connection.execute(f"SELECT COUNT(*) AS total FROM {self._table}").fetchone()["total"]
            if count == 0:
                self._bootstrap_first_superior()
            self._initialized = True

    def _bootstrap_first_superior(self) -> None:
        if settings.is_production:
            username = os.getenv("LOCAL_AUTH_BOOTSTRAP_USERNAME", "").strip()
            password = os.getenv("LOCAL_AUTH_BOOTSTRAP_PASSWORD", "")
            if username and password:
                self.create_account(
                    tenant_id=settings.local_auth_tenant_id,
                    username=username,
                    password=password,
                    role=Role.SUPERIOR.value,
                    display_name=os.getenv("LOCAL_AUTH_BOOTSTRAP_NAME", "Superior Administrator").strip(),
                    email=os.getenv("LOCAL_AUTH_BOOTSTRAP_EMAIL", "").strip() or None,
                    department="Executive",
                )
            return

        if settings.is_development or settings.is_demo:
            for username, password, role, name, department, email in DEMO_ACCOUNTS:
                self.create_account(
                    tenant_id="enterprise-tenant",
                    username=username,
                    password=password,
                    role=role,
                    display_name=name,
                    email=email,
                    department=department,
                    allow_short_password=True,
                )

    def create_account(
        self,
        *,
        tenant_id: str,
        username: str,
        password: str,
        role: str,
        display_name: str,
        email: str | None = None,
        department: str | None = None,
        allow_short_password: bool = False,
    ) -> dict[str, Any]:
        normalized_username = username.strip().casefold()
        if not normalized_username or len(normalized_username) > 50:
            raise ValueError("User ID must contain 1 to 50 characters.")
        if role not in {Role.SUPERIOR.value, Role.SUPERVISOR.value, Role.PROJECT_ENGINEER.value, Role.EMPLOYEE.value}:
            raise ValueError("Choose one of the four supported user roles.")
        if allow_short_password:
            salt = secrets.token_bytes(16)
            digest = hashlib.scrypt(
                password.encode("utf-8"), salt=salt, n=PASSWORD_SCRYPT_N,
                r=PASSWORD_SCRYPT_R, p=PASSWORD_SCRYPT_P, dklen=PASSWORD_KEY_LENGTH,
                maxmem=64 * 1024 * 1024,
            )
            salt_hex, digest_hex = salt.hex(), digest.hex()
        else:
            salt_hex, digest_hex = hash_password(password)

        account_id = str(uuid.uuid4())
        placeholder = "%s" if self._dsn else "?"
        sql = (
            f"INSERT INTO {self._table} "
            "(id, tenant_id, username, password_salt, password_hash, role, display_name, email, department, active) "
            f"VALUES ({', '.join([placeholder] * 10)})"
        )
        try:
            with self._connect() as connection:
                connection.execute(sql, (
                    account_id, tenant_id, normalized_username, salt_hex, digest_hex,
                    role, display_name.strip(), email, department, True,
                ))
                connection.commit()
        except Exception as exc:
            if "unique" in str(exc).casefold() or "duplicate" in str(exc).casefold():
                raise ValueError("That user ID is already in use.") from exc
            raise
        return self.get_account(account_id, tenant_id)

    def authenticate(
        self,
        username: str,
        password: str,
        selected_role: str,
        tenant_id: str = "enterprise-tenant",
    ) -> dict[str, Any] | None:
        self.initialize()
        normalized_username = username.strip().casefold()
        placeholder = "%s" if self._dsn else "?"
        with self._connect() as connection:
            account = connection.execute(
                f"SELECT * FROM {self._table} WHERE tenant_id = {placeholder} AND username = {placeholder} AND active = {('TRUE' if self._dsn else '1')}",
                (tenant_id, normalized_username),
            ).fetchone()
        if not account or account["role"] != selected_role:
            return None
        if not verify_password(password, account["password_salt"], account["password_hash"]):
            return None
        return dict(account)

    def list_accounts(self, tenant_id: str) -> list[dict[str, Any]]:
        self.initialize()
        placeholder = "%s" if self._dsn else "?"
        with self._connect() as connection:
            rows = connection.execute(
                f"SELECT id, username, role, display_name, email, department, active, created_at FROM {self._table} WHERE tenant_id = {placeholder} ORDER BY username",
                (tenant_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_account(self, account_id: str, tenant_id: str) -> dict[str, Any]:
        placeholder = "%s" if self._dsn else "?"
        with self._connect() as connection:
            row = connection.execute(
                f"SELECT id, username, role, display_name, email, department, active, created_at FROM {self._table} WHERE id = {placeholder} AND tenant_id = {placeholder}",
                (account_id, tenant_id),
            ).fetchone()
        if not row:
            raise ValueError("Account not found.")
        return dict(row)

    def delete_account(self, account_id: str, tenant_id: str) -> dict[str, Any]:
        account = self.get_account(account_id, tenant_id)
        placeholder = "%s" if self._dsn else "?"
        with self._connect() as connection:
            connection.execute(
                f"DELETE FROM {self._table} WHERE id = {placeholder} AND tenant_id = {placeholder}",
                (account_id, tenant_id),
            )
            connection.commit()
        return account

    def count_role(self, tenant_id: str, role: str) -> int:
        placeholder = "%s" if self._dsn else "?"
        with self._connect() as connection:
            row = connection.execute(
                f"SELECT COUNT(*) AS total FROM {self._table} WHERE tenant_id = {placeholder} AND role = {placeholder} AND active = {('TRUE' if self._dsn else '1')}",
                (tenant_id, role),
            ).fetchone()
        return int(row["total"])


_account_store: LocalAccountStore | None = None
_account_store_lock = threading.Lock()


def get_local_account_store() -> LocalAccountStore:
    global _account_store
    if _account_store is None:
        with _account_store_lock:
            if _account_store is None:
                dsn = settings.supabase_database_url or settings.database_url
                _account_store = LocalAccountStore(dsn=dsn or "", sqlite_path=settings.local_auth_db_path or None)
    _account_store.initialize()
    return _account_store