from __future__ import annotations

from .abstraction import DatabaseRepository
from .exceptions import DatabaseConfigurationError
from backend.core.resilience import RetryPolicy, retry_idempotent
from .models import QueryRequest, QueryResult
from backend.observability.logging import log_event
import logging
import time

logger = logging.getLogger(__name__)


class PostgreSQLRepository(DatabaseRepository):
    """Read-only PostgreSQL repository backed by psycopg3 connection pooling.

    Credentials are supplied only to this backend integration. Callers receive no
    connection or credential object. The connection is placed in a read-only
    transaction and statement_timeout is applied for each query.
    """

    def __init__(self, dsn: str, *, max_rows: int = 500, max_result_bytes: int = 2_000_000,
                 timeout_ms: int = 5_000, pool_min_size: int = 1, pool_max_size: int = 5, retry_policy: RetryPolicy | None = None):
        if not dsn:
            raise DatabaseConfigurationError("PostgreSQL DSN is required")
        if min(max_rows, max_result_bytes, timeout_ms, pool_min_size, pool_max_size) <= 0:
            raise DatabaseConfigurationError("Database limits must be positive")
        try:
            from psycopg_pool import ConnectionPool
        except ImportError as exc:
            raise DatabaseConfigurationError(
                "PostgreSQL support requires psycopg[binary,pool]"
            ) from exc

        self._max_rows = max_rows
        self._max_result_bytes = max_result_bytes
        self._timeout_ms = timeout_ms
        self._retry_policy = retry_policy or RetryPolicy(attempts=2)
        self._pool = ConnectionPool(
            conninfo=dsn,
            min_size=pool_min_size,
            max_size=pool_max_size,
            kwargs={"autocommit": False},
            open=True,
        )
        import atexit
        atexit.register(self.close)

    def close(self) -> None:
        try:
            self._pool.close(timeout=1.0)
        except Exception:
            pass

    def execute_read(self, request: QueryRequest) -> QueryResult:
        # Parameter values are passed separately to psycopg; they are never interpolated.
        def operation() -> QueryResult:
            with self._pool.connection() as conn:
                with conn.transaction():
                    conn.execute("SET TRANSACTION READ ONLY")
                    conn.execute(f"SET LOCAL statement_timeout = {int(self._timeout_ms)}")
                    with conn.cursor() as cur:
                        cur.execute(request.sql, request.parameters)
                        columns = tuple(desc.name for desc in cur.description)
                        rows: list[tuple[object, ...]] = []
                        total_bytes = 0
                        truncated = False
                        for row in cur:
                            encoded = repr(row).encode("utf-8", errors="replace")
                            if len(rows) >= self._max_rows or total_bytes + len(encoded) > self._max_result_bytes:
                                truncated = True
                                break
                            rows.append(tuple(row))
                            total_bytes += len(encoded)
                        return QueryResult(columns=columns, rows=tuple(rows), truncated=truncated)

        def is_transient(exc: Exception) -> bool:
            # Only transport/connection failures are retryable. SQL syntax,
            # authorization, validation and statement-timeout failures are not.
            if type(exc).__name__ in {"OperationalError", "InterfaceError"}:
                return True
            try:
                import psycopg
                return isinstance(exc, (psycopg.OperationalError, psycopg.InterfaceError))
            except ImportError:
                return False
        started = time.perf_counter()
        try:
            result = retry_idempotent(operation, policy=self._retry_policy, retry_if=is_transient)
        except Exception as exc:
            log_event(logger, "database_query_failed", logging.ERROR, exception_type=type(exc).__name__,
                      duration_ms=round((time.perf_counter() - started) * 1000, 2), retry_attempts=self._retry_policy.attempts)
            raise
        log_event(logger, "database_query_completed", duration_ms=round((time.perf_counter() - started) * 1000, 2),
                  row_count=len(result.rows), truncated=result.truncated)
        return result

    def close(self) -> None:
        self._pool.close()


class PostgreSQLConnectionFactory:
    def __init__(self, dsn: str, **kwargs):
        self._dsn = dsn
        self._kwargs = kwargs

    def create_repository(self) -> PostgreSQLRepository:
        return PostgreSQLRepository(self._dsn, **self._kwargs)
