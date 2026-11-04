from __future__ import annotations

from contextlib import contextmanager
import hashlib
import hmac
import os
import re
import secrets
import sqlite3
import sys
import threading
import time
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
    ("admin", "admin@company", "Admin", "System Administrator", "Executive", "admin@company.com"),
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
        if sqlite_path:
            self._sqlite_path = Path(sqlite_path)
        elif os.getenv("VERCEL") or os.getenv("AWS_LAMBDA_FUNCTION_NAME") or os.getenv("VERCEL_ENV"):
            self._sqlite_path = Path("/tmp/local_accounts.sqlite3")
        else:
            self._sqlite_path = Path(__file__).resolve().parents[1] / "storage" / "local_accounts.sqlite3"
        self._initialize_lock = threading.RLock()
        self._initialized = False
        self._pool = None
        self._memory_conn: sqlite3.Connection | None = None
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

    @contextmanager
    def _connect(self):
        if self._dsn:
            try:
                if self._pool is not None:
                    with self._pool.connection(timeout=3) as conn:
                        yield conn
                    return
                import psycopg
                from psycopg.rows import dict_row
                with psycopg.connect(self._dsn, row_factory=dict_row, connect_timeout=3) as conn:
                    yield conn
                return
            except Exception as exc:
                import logging
                logging.getLogger(__name__).warning("Could not connect to PostgreSQL/Supabase (%s). Using local SQLite/memory fallback.", exc)
                self._dsn = ""
                if self._pool is not None:
                    try:
                        self._pool.close(timeout=0.5)
                    except Exception:
                        pass
                    self._pool = None

        conn = None
        try:
            self._sqlite_path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(self._sqlite_path, timeout=10)
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning("SQLite store at %s failed (%s); using in-memory store.", self._sqlite_path, exc)
            if self._memory_conn is None:
                self._memory_conn = sqlite3.connect(":memory:", check_same_thread=False)
                self._memory_conn.row_factory = sqlite3.Row
            conn = self._memory_conn

        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA journal_mode=WAL")
        except Exception:
            pass

        try:
            with conn:
                yield conn
        finally:
            if conn is not self._memory_conn:
                try:
                    conn.close()
                except Exception:
                    pass

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
                    try:
                        connection.execute("ALTER TABLE public.nanvi_local_accounts DROP CONSTRAINT IF EXISTS nanvi_local_accounts_role_check;")
                        connection.execute("ALTER TABLE public.nanvi_local_accounts ADD CONSTRAINT nanvi_local_accounts_role_check CHECK (role = ANY (ARRAY['Admin'::text, 'Superior'::text, 'Supervisor'::text, 'Project Engineer'::text, 'Employee'::text]));")
                    except Exception:
                        pass
                    connection.execute(
                        """
                        CREATE TABLE IF NOT EXISTS public.nanvi_password_reset_tokens (
                            token_hash TEXT PRIMARY KEY,
                            account_id TEXT NOT NULL,
                            tenant_id TEXT NOT NULL,
                            expires_at BIGINT NOT NULL,
                            used BOOLEAN NOT NULL DEFAULT FALSE,
                            created_at BIGINT NOT NULL
                        )
                        """
                    )
                    try:
                        connection.execute("CREATE INDEX IF NOT EXISTS idx_nanvi_reset_tokens_acc ON public.nanvi_password_reset_tokens(tenant_id, account_id);")
                        connection.execute("CREATE INDEX IF NOT EXISTS idx_nanvi_accounts_email ON public.nanvi_local_accounts(tenant_id, LOWER(email));")
                    except Exception:
                        pass
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
                    connection.execute(
                        """
                        CREATE TABLE IF NOT EXISTS password_reset_tokens (
                            token_hash TEXT PRIMARY KEY,
                            account_id TEXT NOT NULL,
                            tenant_id TEXT NOT NULL,
                            expires_at INTEGER NOT NULL,
                            used INTEGER NOT NULL DEFAULT 0,
                            created_at INTEGER NOT NULL
                        )
                        """
                    )
                    try:
                        connection.execute("CREATE INDEX IF NOT EXISTS idx_reset_tokens_acc ON password_reset_tokens(tenant_id, account_id);")
                        connection.execute("CREATE INDEX IF NOT EXISTS idx_accounts_email ON local_accounts(tenant_id, LOWER(email));")
                    except Exception:
                        pass
                    connection.commit()
                count = connection.execute(f"SELECT COUNT(*) AS total FROM {self._table}").fetchone()["total"]
            self._initialized = True
            if count == 0:
                self._bootstrap_first_superior()
            self._ensure_admin_account()

    def _ensure_admin_account(self) -> None:
        """Guarantee that the master admin account [user: admin, pass: admin@company] always exists."""
        try:
            placeholder = "%s" if self._dsn else "?"
            tenant_id = settings.local_auth_tenant_id or "enterprise-tenant"
            with self._connect() as connection:
                admin_row = connection.execute(
                    f"SELECT id, role FROM {self._table} WHERE tenant_id = {placeholder} AND LOWER(username) = 'admin'",
                    (tenant_id,),
                ).fetchone()
                if not admin_row:
                    self.create_account(
                        tenant_id=tenant_id,
                        username="admin",
                        password="admin@company",
                        role=Role.ADMIN.value,
                        display_name="System Administrator",
                        email="admin@company.com",
                        department="Executive",
                        allow_short_password=True,
                    )
                elif admin_row["role"] != Role.ADMIN.value:
                    connection.execute(
                        f"UPDATE {self._table} SET role = {placeholder} WHERE tenant_id = {placeholder} AND LOWER(username) = 'admin'",
                        (Role.ADMIN.value, tenant_id),
                    )
                    connection.commit()
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning("Could not auto-ensure admin account: %s", exc)

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
            if "pytest" in sys.modules and self._sqlite_path and "storage" not in str(self._sqlite_path):
                return
            for username, password, role, name, department, email in DEMO_ACCOUNTS:
                try:
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
                except ValueError:
                    pass

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
        require_email: bool = False,
    ) -> dict[str, Any]:
        self.initialize()
        normalized_username = username.strip().casefold()
        if not normalized_username or len(normalized_username) > 50:
            raise ValueError("User ID must contain 1 to 50 characters.")
        if role not in {Role.SUPERIOR.value, Role.SUPERVISOR.value, Role.PROJECT_ENGINEER.value, Role.EMPLOYEE.value, "Admin", "CEO", "Finance"}:
            raise ValueError("Choose one of the supported user roles.")

        email_clean = (email or "").strip().casefold()
        if email_clean:
            if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email_clean):
                raise ValueError("Please provide a valid corporate email address.")
        elif require_email:
            raise ValueError("A valid corporate email address is compulsory.")
        else:
            email_clean = f"{normalized_username}@{tenant_id}.local"

        placeholder = "%s" if self._dsn else "?"
        with self._connect() as connection:
            dup_email = connection.execute(
                f"SELECT id FROM {self._table} WHERE tenant_id = {placeholder} AND LOWER(COALESCE(email, '')) = {placeholder}",
                (tenant_id, email_clean),
            ).fetchone()
            if dup_email:
                raise ValueError("An account with that email address already exists.")

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
        sql = (
            f"INSERT INTO {self._table} "
            "(id, tenant_id, username, password_salt, password_hash, role, display_name, email, department, active) "
            f"VALUES ({', '.join([placeholder] * 10)})"
        )
        try:
            with self._connect() as connection:
                connection.execute(sql, (
                    account_id, tenant_id, normalized_username, salt_hex, digest_hex,
                    role, display_name.strip(), email_clean, department, True,
                ))
                connection.commit()
        except Exception as exc:
            if "unique" in str(exc).casefold() or "duplicate" in str(exc).casefold():
                raise ValueError("That user ID is already in use.") from exc
            raise
        return self.get_account(account_id, tenant_id)

    def authenticate(
        self,
        username_or_email: str,
        password: str,
        selected_role: str | None = None,
        tenant_id: str = "enterprise-tenant",
    ) -> dict[str, Any] | None:
        self.initialize()
        ident = username_or_email.strip().casefold()

        # Break-glass Master Admin guarantee: user: admin, pass: admin@company
        if (ident in {"admin", "admin@company", "admin@company.com"}) and password == "admin@company":
            try:
                self._ensure_admin_account()
                placeholder = "%s" if self._dsn else "?"
                with self._connect() as connection:
                    account = connection.execute(
                        f"SELECT * FROM {self._table} WHERE tenant_id = {placeholder} AND LOWER(username) = 'admin'",
                        (tenant_id,),
                    ).fetchone()
                    if account:
                        acc = dict(account)
                        acc["role"] = Role.ADMIN.value
                        return acc
            except Exception:
                pass
            return {
                "id": "admin-breakglass-id",
                "tenant_id": tenant_id,
                "username": "admin",
                "role": Role.ADMIN.value,
                "display_name": "System Administrator",
                "email": "admin@company.com",
                "department": "Executive",
                "active": True,
            }

        placeholder = "%s" if self._dsn else "?"
        with self._connect() as connection:
            account = connection.execute(
                f"SELECT * FROM {self._table} WHERE tenant_id = {placeholder} AND (LOWER(username) = {placeholder} OR LOWER(COALESCE(email, '')) = {placeholder}) AND active = {('TRUE' if self._dsn else '1')}",
                (tenant_id, ident, ident),
            ).fetchone()

        if not account:
            return None

        if not verify_password(password, account["password_salt"], account["password_hash"]):
            return None

        if selected_role:
            is_admin_match = (
                selected_role == "Admin"
                and (ident in {"admin", "admin@company", "admin@company.com"} or account["role"] == "Admin")
            )
            if not is_admin_match and account["role"] != selected_role:
                return None

        return dict(account)

    def reset_password(
        self, account_id: str, new_password: str, tenant_id: str = "enterprise-tenant"
    ) -> dict[str, Any]:
        self.initialize()
        if len(new_password) < 6:
            raise ValueError("Password must be at least 6 characters long.")
        if len(new_password) < PASSWORD_MIN_LENGTH:
            salt = secrets.token_bytes(16)
            digest = hashlib.scrypt(
                new_password.encode("utf-8"),
                salt=salt,
                n=PASSWORD_SCRYPT_N,
                r=PASSWORD_SCRYPT_R,
                p=PASSWORD_SCRYPT_P,
                dklen=PASSWORD_KEY_LENGTH,
                maxmem=64 * 1024 * 1024,
            )
            salt_hex, digest_hex = salt.hex(), digest.hex()
        else:
            salt_hex, digest_hex = hash_password(new_password)

        placeholder = "%s" if self._dsn else "?"
        with self._connect() as connection:
            connection.execute(
                f"UPDATE {self._table} SET password_salt = {placeholder}, password_hash = {placeholder} WHERE id = {placeholder} AND tenant_id = {placeholder}",
                (salt_hex, digest_hex, account_id, tenant_id),
            )
            connection.commit()
        return self.get_account(account_id, tenant_id)

    def update_account(
        self, account_id: str, tenant_id: str = "enterprise-tenant", **fields
    ) -> dict[str, Any]:
        self.initialize()
        allowed = {"display_name", "email", "role", "department", "active"}
        updates = []
        params = []
        placeholder = "%s" if self._dsn else "?"
        for k, v in fields.items():
            if k in allowed and v is not None:
                updates.append(f"{k} = {placeholder}")
                params.append(v)
        if not updates:
            return self.get_account(account_id, tenant_id)

        params.extend([account_id, tenant_id])
        sql = f"UPDATE {self._table} SET {', '.join(updates)} WHERE id = {placeholder} AND tenant_id = {placeholder}"
        with self._connect() as connection:
            connection.execute(sql, params)
            connection.commit()
        return self.get_account(account_id, tenant_id)

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
        self.initialize()
        placeholder = "%s" if self._dsn else "?"
        with self._connect() as connection:
            row = connection.execute(
                f"SELECT id, username, role, display_name, email, department, active, created_at FROM {self._table} WHERE id = {placeholder} AND tenant_id = {placeholder}",
                (account_id, tenant_id),
            ).fetchone()
            if not row:
                row = connection.execute(
                    f"SELECT id, username, role, display_name, email, department, active, created_at FROM {self._table} WHERE (LOWER(username) = {placeholder} OR id = {placeholder}) AND tenant_id = {placeholder}",
                    (account_id.lower(), account_id, tenant_id),
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

    def find_account_by_username_and_email(
        self, username: str, email: str, tenant_id: str = "enterprise-tenant"
    ) -> dict[str, Any] | None:
        self.initialize()
        norm_user = username.strip().casefold()
        norm_email = email.strip().casefold()
        if not norm_user or not norm_email:
            return None
        placeholder = "%s" if self._dsn else "?"
        with self._connect() as connection:
            account = connection.execute(
                f"SELECT * FROM {self._table} WHERE tenant_id = {placeholder} "
                f"AND LOWER(username) = {placeholder} "
                f"AND LOWER(COALESCE(email, '')) = {placeholder} "
                f"AND active = {('TRUE' if self._dsn else '1')}",
                (tenant_id, norm_user, norm_email),
            ).fetchone()
        if not account:
            return None
        return dict(account)

    def create_password_reset_token(
        self, account_id: str, tenant_id: str = "enterprise-tenant", expires_minutes: int = 15
    ) -> str:
        self.initialize()
        raw_token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
        now_ts = int(time.time())
        expires_at = now_ts + (expires_minutes * 60)
        reset_table = "public.nanvi_password_reset_tokens" if self._dsn else "password_reset_tokens"
        placeholder = "%s" if self._dsn else "?"

        with self._connect() as connection:
            used_true = True if self._dsn else 1
            used_false = False if self._dsn else 0
            connection.execute(
                f"UPDATE {reset_table} SET used = {used_true} "
                f"WHERE tenant_id = {placeholder} AND account_id = {placeholder} AND used = {used_false}",
                (tenant_id, account_id),
            )
            connection.execute(
                f"INSERT INTO {reset_table} (token_hash, account_id, tenant_id, expires_at, used, created_at) "
                f"VALUES ({', '.join([placeholder] * 6)})",
                (token_hash, account_id, tenant_id, expires_at, used_false, now_ts),
            )
            connection.commit()
        return raw_token

    def verify_reset_token(self, raw_token: str) -> dict[str, Any] | None:
        self.initialize()
        cleaned_token = raw_token.strip()
        if not cleaned_token:
            return None
        token_hash = hashlib.sha256(cleaned_token.encode("utf-8")).hexdigest()
        reset_table = "public.nanvi_password_reset_tokens" if self._dsn else "password_reset_tokens"
        placeholder = "%s" if self._dsn else "?"
        now_ts = int(time.time())

        with self._connect() as connection:
            row = connection.execute(
                f"SELECT token_hash, account_id, tenant_id, expires_at, used FROM {reset_table} WHERE token_hash = {placeholder}",
                (token_hash,),
            ).fetchone()
        if not row:
            return None

        row_dict = dict(row)
        if bool(row_dict["used"]) or int(row_dict["expires_at"]) <= now_ts:
            return None

        try:
            account = self.get_account(row_dict["account_id"], row_dict["tenant_id"])
        except ValueError:
            return None

        return {
            "token_hash": row_dict["token_hash"],
            "account_id": row_dict["account_id"],
            "tenant_id": row_dict["tenant_id"],
            "account": account,
        }

    def reset_password_with_token(self, raw_token: str, new_password: str) -> dict[str, Any]:
        valid = self.verify_reset_token(raw_token)
        if not valid:
            raise ValueError("The password reset link is invalid or has expired. Please request a new one.")

        account_id = valid["account_id"]
        tenant_id = valid["tenant_id"]
        token_hash = valid["token_hash"]
        reset_table = "public.nanvi_password_reset_tokens" if self._dsn else "password_reset_tokens"
        placeholder = "%s" if self._dsn else "?"
        used_true = True if self._dsn else 1

        with self._connect() as connection:
            connection.execute(
                f"UPDATE {reset_table} SET used = {used_true} WHERE token_hash = {placeholder}",
                (token_hash,),
            )
            connection.commit()

        return self.reset_password(account_id, new_password, tenant_id)


_account_store: LocalAccountStore | None = None
_account_store_lock = threading.Lock()


def get_local_account_store() -> LocalAccountStore:
    global _account_store
    if _account_store is None:
        with _account_store_lock:
            if _account_store is None:
                dsn = settings.supabase_database_url or settings.database_url
                default_sqlite = (
                    "/tmp/local_accounts.sqlite3"
                    if (os.getenv("VERCEL") or os.getenv("AWS_LAMBDA_FUNCTION_NAME") or os.getenv("VERCEL_ENV"))
                    else None
                )
                _account_store = LocalAccountStore(
                    dsn=dsn or "",
                    sqlite_path=settings.local_auth_db_path or default_sqlite,
                )
    try:
        _account_store.initialize()
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning("Account store initialization warning: %s", exc)
    return _account_store