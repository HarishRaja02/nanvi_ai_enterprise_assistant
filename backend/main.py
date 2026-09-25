from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.api.routes import router
from backend.api.report_routes import router as report_router
from backend.api.source_routes import router as source_router
from backend.api.chat_routes import router as chat_router
from backend.core.config import settings
from backend.observability import RequestContextMiddleware, configure_logging, configure_telemetry
from backend.security.headers import SecurityHeadersMiddleware
from backend.security.rate_limiting import InMemoryFixedWindowRateLimiter, NoOpRateLimiter, RateLimitExceeded, RedisFixedWindowRateLimiter

configure_logging(settings.log_level)
configure_telemetry(settings.otel_enabled, settings.otel_service_name, settings.otel_exporter_otlp_endpoint)

app = FastAPI(title=settings.app_name, debug=settings.debug)
app.add_middleware(RequestContextMiddleware)
app.add_middleware(SecurityHeadersMiddleware, hsts_enabled=settings.hsts_enabled)

if settings.cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
        expose_headers=["X-Request-ID"],
    )

if settings.app_env == "production" and settings.redis_url:
    _rate_limiter = RedisFixedWindowRateLimiter(
        settings.redis_url,
        settings.rate_limit_requests,
        settings.rate_limit_window_seconds,
    )
else:
    _rate_limiter = InMemoryFixedWindowRateLimiter(
        settings.rate_limit_requests,
        settings.rate_limit_window_seconds,
    ) if settings.app_env in {"testing", "production"} else NoOpRateLimiter()

@app.middleware("http")
async def rate_limit(request: Request, call_next):
    if request.url.path in {"/api/health", "/api/health/ready"}:
        return await call_next(request)
    key = request.headers.get("X-Forwarded-For", request.client.host if request.client else "unknown").split(",")[0].strip()
    try:
        _rate_limiter.check(key)
    except RateLimitExceeded:
        return JSONResponse(status_code=429, content={"detail": "Rate limit exceeded"}, headers={"Retry-After": str(settings.rate_limit_window_seconds)})
    return await call_next(request)

from backend.api.email_routes import router as email_router
from backend.api.settings_routes import router as settings_router
from backend.api.voice_routes import router as voice_router
from backend.connections.routes import router as connections_router
from backend.connections.oauth_routes import router as connections_oauth_router, auth_router as connections_auth_router

app.include_router(router, prefix="/api")
app.include_router(router)
app.include_router(report_router, prefix="/api")
app.include_router(report_router)
app.include_router(source_router, prefix="/api")
app.include_router(source_router)
app.include_router(chat_router, prefix="/api")
app.include_router(chat_router)
app.include_router(voice_router, prefix="/api")
app.include_router(voice_router)
app.include_router(email_router, prefix="/api")
app.include_router(email_router)
app.include_router(settings_router, prefix="/api")
app.include_router(settings_router)
app.include_router(connections_router)
app.include_router(connections_oauth_router)
app.include_router(connections_auth_router)


# Development-only endpoints (token generation for local testing)
if settings.app_env == "development" and settings.jwt_secret:
    from backend.api.dev_routes import router as dev_router
    app.include_router(dev_router, prefix="/api")
    app.include_router(dev_router)

