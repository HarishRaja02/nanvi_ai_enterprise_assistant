from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv

# Load .env file from project root if present
_env_path = Path(__file__).resolve().parent.parent.parent / ".env"
load_dotenv(_env_path, override=True)


Environment = Literal["development", "testing", "production"]


@dataclass(frozen=True)
class Settings:
    app_env: Environment
    app_name: str
    debug: bool
    oidc_issuer_url: str
    oidc_client_id: str
    oidc_client_secret: str
    oidc_redirect_uri: str
    oidc_jwks_url: str
    oidc_audience: str
    oidc_algorithms: tuple[str, ...]
    company_file_roots: tuple[tuple[str, str], ...]
    company_file_max_size_bytes: int
    database_url: str
    database_pool_min_size: int
    database_pool_max_size: int
    database_statement_timeout_ms: int
    redis_url: str
    rate_limit_requests: int
    rate_limit_window_seconds: int
    request_timeout_seconds: float
    log_level: str
    otel_enabled: bool
    otel_service_name: str
    otel_exporter_otlp_endpoint: str
    cors_origins: tuple[str, ...]
    hsts_enabled: bool
    llm_provider: str
    llm_model: str
    groq_api_key: str
    
    google_client_id: str
    google_client_secret: str
    google_redirect_uri: str
    gmail_refresh_token: str
    gmail_access_token: str
    jwt_secret: str
    
    tavily_api_key: str
    supabase_url: str
    supabase_key: str
    supabase_database_url: str
    retrieval_v2_enabled: bool = True
    groq_max_concurrency: int = 3
    groq_token_budget_ceiling: int = 3500
    groq_max_retries: int = 3
    encryption_key: str = ""
    encryption_key_id: str = "v1"
    allow_legacy_gmail_token: bool = False
    github_client_id: str = ""
    github_client_secret: str = ""
    oauth_redirect_base_url: str = ""
    demo_auth_enabled: bool = False
    
    
    
    
    @classmethod
    def from_env(cls) -> "Settings":
        env = os.getenv("APP_ENV", "development").strip().lower()
        if env not in {"development", "testing", "production"}:
            raise ValueError("APP_ENV must be development, testing, or production")

        def boolean(name: str, default: bool) -> bool:
            return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}

        def integer(name: str, default: int) -> int:
            value = int(os.getenv(name, str(default)))
            if value <= 0:
                raise ValueError(f"{name} must be positive")
            return value

        def number(name: str, default: float) -> float:
            value = float(os.getenv(name, str(default)))
            if value <= 0:
                raise ValueError(f"{name} must be positive")
            return value

        origins = tuple(x.strip() for x in os.getenv("CORS_ORIGINS", "").split(",") if x.strip())
        return cls(
            app_env=env,  # type: ignore[arg-type]
            app_name=os.getenv("APP_NAME", "Nanvi AI Enterprise Assistant"),
            debug=False if env == "production" else boolean("DEBUG", env == "development"),
            oidc_issuer_url=os.getenv("OIDC_ISSUER_URL", "").rstrip("/"),
            oidc_client_id=os.getenv("OIDC_CLIENT_ID", ""),
            oidc_client_secret=os.getenv("OIDC_CLIENT_SECRET", ""),
            oidc_redirect_uri=os.getenv("OIDC_REDIRECT_URI", ""),
            oidc_jwks_url=os.getenv("OIDC_JWKS_URL", ""),
            oidc_audience=os.getenv("OIDC_AUDIENCE", ""),
            oidc_algorithms=tuple(x.strip() for x in os.getenv("OIDC_ALGORITHMS", "RS256").split(",") if x.strip()),
            company_file_roots=_parse_company_roots(os.getenv("COMPANY_FILE_ROOTS", ""), env),
            company_file_max_size_bytes=integer("COMPANY_FILE_MAX_SIZE_BYTES", 10 * 1024 * 1024),
            database_url=os.getenv("DATABASE_URL", ""),
            database_pool_min_size=integer("DATABASE_POOL_MIN_SIZE", 2),
            database_pool_max_size=integer("DATABASE_POOL_MAX_SIZE", 10),
            database_statement_timeout_ms=integer("DATABASE_STATEMENT_TIMEOUT_MS", 5000),
            redis_url=os.getenv("REDIS_URL", ""),
            rate_limit_requests=integer("RATE_LIMIT_REQUESTS", 60),
            rate_limit_window_seconds=integer("RATE_LIMIT_WINDOW_SECONDS", 60),
            request_timeout_seconds=number("REQUEST_TIMEOUT_SECONDS", 30.0),
            log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
            otel_enabled=boolean("OTEL_ENABLED", False),
            otel_service_name=os.getenv("OTEL_SERVICE_NAME", "nanvi-api"),
            otel_exporter_otlp_endpoint=os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", ""),
            cors_origins=origins,
            hsts_enabled=True if env == "production" else boolean("HSTS_ENABLED", False),
            llm_provider=os.getenv("LLM_PROVIDER", "groq").strip().lower(),
            llm_model=os.getenv("LLM_MODEL", "llama-3.3-70b-versatile").strip(),
            groq_api_key=os.getenv("GROQ_API_KEY", ""),
            jwt_secret=os.getenv("JWT_SECRET", ""),
            demo_auth_enabled=boolean("DEMO_AUTH_ENABLED", False),
            google_client_id=os.getenv("GOOGLE_CLIENT_ID", "").strip(),
            google_client_secret=os.getenv("GOOGLE_CLIENT_SECRET", "").strip(),
            google_redirect_uri=os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:5173").strip(),
            gmail_refresh_token=os.getenv("GMAIL_REFRESH_TOKEN", "").strip(),
            gmail_access_token=os.getenv("GMAIL_ACCESS_TOKEN", "").strip(),
            tavily_api_key=os.getenv("TAVILY_API_KEY", "").strip(),
            supabase_url=os.getenv("SUPABASE_URL", "").strip(),
            supabase_key=os.getenv("SUPABASE_KEY", "").strip(),
            supabase_database_url=os.getenv("SUPABASE_DATABASE_URL", "").strip(),
            retrieval_v2_enabled=boolean("RETRIEVAL_V2_ENABLED", True),
            groq_max_concurrency=integer("GROQ_MAX_CONCURRENCY", 3),
            groq_token_budget_ceiling=integer("GROQ_TOKEN_BUDGET_CEILING", 3500),
            groq_max_retries=integer("GROQ_MAX_RETRIES", 3),
            encryption_key=os.getenv("ENCRYPTION_KEY", "").strip(),
            encryption_key_id=os.getenv("ENCRYPTION_KEY_ID", "v1").strip(),
            allow_legacy_gmail_token=boolean("ALLOW_LEGACY_GMAIL_TOKEN", False),
            github_client_id=os.getenv("GITHUB_CLIENT_ID", "").strip(),
            github_client_secret=os.getenv("GITHUB_CLIENT_SECRET", "").strip(),
            oauth_redirect_base_url=os.getenv("OAUTH_REDIRECT_BASE_URL", "").strip().rstrip("/"),
        )


def _parse_company_roots(value: str, env: Environment) -> tuple[tuple[str, str], ...]:
    expected = ("Customers", "Finance", "HR", "Projects", "Contracts")
    if not value.strip():
        if env == "production" and not os.getenv("VERCEL"):
            raise ValueError("COMPANY_FILE_ROOTS must explicitly configure Customers, Finance, HR, Projects and Contracts")
        return tuple()
    entries = []
    for item in value.split(";"):
        if "=" not in item:
            raise ValueError("COMPANY_FILE_ROOTS entries must be Name=Path")
        name, path = (x.strip() for x in item.split("=", 1))
        entries.append((name, path))
    names = {name.casefold() for name, _ in entries}
    if set(names) != {x.casefold() for x in expected}:
        raise ValueError("COMPANY_FILE_ROOTS must explicitly contain exactly Customers, Finance, HR, Projects and Contracts")
    return tuple(entries)


settings = Settings.from_env()
