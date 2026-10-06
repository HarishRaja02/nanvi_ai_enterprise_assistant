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

def _probe_uecp() -> dict[str, Any]:
    try:
        from backend.uecp import get_uecp_config, get_uecp_service
        cfg = get_uecp_config()
        if not cfg.enabled:
            return {"status": "skipped", "info": "UECP not enabled"}
        health = get_uecp_service().client.check_health()
        if health["reachable"]:
            return {"status": "up"}
        if settings.is_production:
            return {"status": "down", "error": "UECP unreachable"}
        return {"status": "skipped", "info": "UECP unreachable in development"}
    except Exception as exc:
        if settings.is_production:
            return {"status": "down", "error": str(exc)}
        return {"status": "skipped", "info": f"UECP probe error: {exc}"}


@router.get("/health/uecp")
async def uecp_health() -> dict[str, bool]:
    """Safe backend health/integration status endpoint for UECP."""
    from backend.uecp import get_uecp_service
    return get_uecp_service().client.check_health()


@router.get("/health/ready")
async def readiness() -> Any:
    """Comprehensive readiness probe checking DB, Redis, LLM, Storage, OAuth, and UECP."""
    deps = {
        "database": _probe_database(),
        "redis": _probe_redis(),
        "llm": _probe_llm(),
        "storage": _probe_storage(),
        "oauth": _probe_oauth(),
        "uecp": _probe_uecp(),
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


@router.get("/uecp/status")
async def uecp_status(user: UserIdentity = Depends(get_current_user)) -> dict[str, Any]:
    """Safe authorization state for frontend consumption."""
    from backend.uecp import get_uecp_service
    safe_state = get_uecp_service().get_safe_state(organization_id=user.tenant_id)
    return safe_state.to_dict()


@router.get("/auth/me")
async def current_user(user: UserIdentity = Depends(get_current_user)) -> UserIdentity:
    from backend.uecp import get_uecp_service
    safe_uecp = get_uecp_service().get_safe_state(organization_id=user.tenant_id)
    return UserIdentity(
        subject=user.subject,
        issuer=user.issuer,
        email=user.email,
        name=user.name,
        tenant_id=user.tenant_id,
        department=user.department,
        roles=user.roles,
        uecp=safe_uecp.to_dict(),
    )
