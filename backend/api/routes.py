from typing import Any
import logging
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from backend.core.config import settings
from backend.security.dependencies import get_current_user
from backend.security.models import UserIdentity

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/health")
async def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "app_mode": settings.app_mode,
        "is_production": settings.is_production,
        "allows_synthetic_data": settings.allows_synthetic_data,
    }


@router.get("/v1/health")
async def health_v1() -> dict[str, Any]:
    return {
        "status": "ok",
        "app_mode": settings.app_mode,
        "is_production": settings.is_production,
        "allows_synthetic_data": settings.allows_synthetic_data,
    }


@router.get("/health/live")
async def liveness() -> dict[str, str]:
    """Trivial liveness probe with zero external dependencies."""
    return {"status": "ok"}


def _probe_database() -> dict[str, Any]:
    dsn = settings.supabase_database_url or settings.database_url
    if dsn and settings.is_production:
        try:
            import psycopg
            with psycopg.connect(dsn, connect_timeout=2) as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
                    cur.fetchone()
            return {"status": "up", "backend": "postgresql"}
        except Exception as exc:
            return {"status": "down", "error": str(exc), "backend": "postgresql"}
    elif dsn:
        try:
            import psycopg
            with psycopg.connect(dsn, connect_timeout=1) as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
                    cur.fetchone()
            return {"status": "up", "backend": "postgresql"}
        except Exception:
            pass

    if settings.is_production:
        return {"status": "down", "error": "No PostgreSQL database URL configured in production"}

    # In dev/demo: check SQLite
    try:
        from backend.integrations.database.sqlite import SQLiteEnterpriseRepository
        from backend.integrations.database.models import QueryRequest
        repo = SQLiteEnterpriseRepository(db_path=":memory:")
        res = repo.execute_read(QueryRequest(sql="SELECT 1"))
        return {"status": "up", "backend": "sqlite"}
    except Exception as exc:
        return {"status": "down", "error": str(exc), "backend": "sqlite"}


def _probe_redis() -> dict[str, Any]:
    if not settings.redis_url:
        return {"status": "skipped", "info": "Redis URL not configured"}
    try:
        import redis
        client = redis.Redis.from_url(settings.redis_url, socket_timeout=1.0)
        client.ping()
        return {"status": "up"}
    except Exception as exc:
        if not settings.is_production:
            return {"status": "skipped", "info": f"Redis unavailable in dev: {exc}"}
        return {"status": "down", "error": str(exc)}


def _probe_llm() -> dict[str, Any]:
    if settings.is_production:
        has_key = bool(settings.groq_api_key or getattr(settings, "openai_api_key", None))
        if not has_key:
            return {"status": "down", "error": "No LLM API key configured in production"}
        return {"status": "up", "provider": settings.llm_provider, "model": settings.llm_model}
    return {
        "status": "up",
        "provider": settings.llm_provider if settings.groq_api_key else "deterministic_fallback",
    }


def _probe_storage() -> dict[str, Any]:
    try:
        storage_dir = Path(__file__).resolve().parent.parent / "storage"
        storage_dir.mkdir(parents=True, exist_ok=True)
        test_file = storage_dir / ".write_probe"
        test_file.write_text("ok", encoding="utf-8")
        test_file.unlink(missing_ok=True)
        return {"status": "up", "path": str(storage_dir)}
    except Exception as exc:
        return {"status": "down", "error": str(exc)}


def _probe_oauth() -> dict[str, Any]:
    client_id = settings.google_client_id
    client_secret = settings.google_client_secret
    if client_id and not client_secret:
        return {"status": "down", "error": "google_client_id is present but google_client_secret is missing"}
    if client_id and client_secret:
        return {"status": "up", "provider": "google"}
    return {"status": "skipped", "info": "OAuth not configured"}


@router.get("/health/ready")
async def readiness() -> Any:
    """Comprehensive readiness probe checking DB, Redis, LLM, Storage, and OAuth."""
    deps = {
        "database": _probe_database(),
        "redis": _probe_redis(),
        "llm": _probe_llm(),
        "storage": _probe_storage(),
        "oauth": _probe_oauth(),
    }

    is_any_down = any(dep.get("status") == "down" for dep in deps.values())

    if is_any_down:
        return JSONResponse(
            status_code=503,
            content={
                "status": "unavailable",
                "detail": "DEPENDENCY_UNAVAILABLE: One or more required dependencies are unavailable",
                "app_mode": settings.app_mode,
                "is_production": settings.is_production,
                "dependencies": deps,
            },
        )

    return {
        "status": "ready",
        "app_mode": settings.app_mode,
        "is_production": settings.is_production,
        "dependencies": deps,
    }


@router.get("/auth/me")
async def current_user(user: UserIdentity = Depends(get_current_user)) -> UserIdentity:
    return user
