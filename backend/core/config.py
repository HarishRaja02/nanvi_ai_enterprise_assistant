from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv

# Load .env file from project root if present
_env_path = Path(__file__).resolve().parent.parent.parent / ".env"
load_dotenv(_env_path, override=True)


AppMode = Literal["development", "demo", "production", "testing"]
Environment = AppMode


@dataclass(frozen=True)
class Settings:
    app_mode: AppMode
    app_env: str
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
    rag_relevance_threshold: float = 25.0
    local_auth_enabled: bool = True
    local_auth_db_path: str = ""
    local_auth_tenant_id: str = "enterprise-tenant"
    openai_api_key: str = ""
    realtime_voice_enabled: bool = False
    realtime_voice_model: str = "gpt-live-1"

    @property
    def is_production(self) -> bool:
        return self.app_mode == "production"

    @property
    def is_demo(self) -> bool:
        return self.app_mode == "demo"

    @property
    def is_development(self) -> bool:
        return self.app_mode == "development"

    @property
    def is_testing(self) -> bool:
        return self.app_mode == "testing"

    @property
    def allows_synthetic_data(self) -> bool:
        return self.app_mode in {"development", "demo"}

    def validate_production_configuration(self) -> None:
        """Fail-fast validation for production runtime."""
        if not self.is_production:
            return

        from backend.core.exceptions import ConfigurationError

        errors: list[str] = []

        # 1. Database URL
        if not (self.database_url or self.supabase_database_url):
            errors.append("DATABASE_URL or SUPABASE_DATABASE_URL must be configured")
        else:
            target_db = self.supabase_database_url or self.database_url
            if target_db and ("localhost" in target_db.lower() or "127.0.0.1" in target_db):
                errors.append(
                    "DATABASE_URL or SUPABASE_DATABASE_URL points to 'localhost' or '127.0.0.1'. "
                    "Cloud deployments (Vercel, AWS, Azure) cannot connect to a local database. "
                    "Please provide your Supabase cloud PostgreSQL connection string from Supabase -> Project Settings -> Database."
                )

        # 2. Secret keys / auth
        if not self.jwt_secret and not (self.oidc_issuer_url and self.oidc_client_id and self.oidc_jwks_url):
            errors.append("JWT_SECRET or complete OIDC configuration (OIDC_ISSUER_URL, OIDC_CLIENT_ID, OIDC_JWKS_URL) must be configured")

        # 3. LLM key
        if self.llm_provider == "groq" and not self.groq_api_key:
            errors.append("GROQ_API_KEY must be configured when LLM_PROVIDER is 'groq'")

        # 4. Demo flags must be OFF
        if self.demo_auth_enabled:
            errors.append("DEMO_AUTH_ENABLED must be False in production")

        if self.local_auth_enabled and not self.jwt_secret:
            errors.append("JWT_SECRET must be configured when LOCAL_AUTH_ENABLED is true")
        if self.local_auth_enabled:
            bootstrap_username = os.getenv("LOCAL_AUTH_BOOTSTRAP_USERNAME", "").strip()
            bootstrap_password = os.getenv("LOCAL_AUTH_BOOTSTRAP_PASSWORD", "")
            if not bootstrap_username or len(bootstrap_password) < 12:
                errors.append("LOCAL_AUTH_BOOTSTRAP_USERNAME and a 12-character LOCAL_AUTH_BOOTSTRAP_PASSWORD are required")

        if self.debug:
            errors.append("DEBUG must be False in production")

        if self.allow_legacy_gmail_token:
            errors.append("ALLOW_LEGACY_GMAIL_TOKEN must be False in production")

        if errors:
            raise ConfigurationError(
                "Production fail-fast validation failed:\n  - " + "\n  - ".join(errors)
            )
    
    @classmethod
    def from_env(cls) -> "Settings":
        raw_mode = os.getenv("APP_MODE")
        if raw_mode is not None and raw_mode.strip():
            mode = raw_mode.strip().lower()
            if mode not in {"development", "demo", "production", "testing"}:
                raise ValueError(f"Invalid APP_MODE: '{mode}'. Must be development, demo, production, or testing")
        else:
            raw_env = os.getenv("APP_ENV")
            if raw_env is not None and raw_env.strip():
                mode = raw_env.strip().lower()
                if mode not in {"development", "demo", "production", "testing"}:
                    raise ValueError(f"Invalid APP_ENV: '{mode}'. Must be development, demo, production, or testing")
            else:
                # FAIL CLOSED: Default to production if unset
                mode = "production"

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
        openai_api_key = os.getenv("OPENAI_API_KEY", "").strip()
        return cls(
            app_mode=mode,  # type: ignore[arg-type]
            app_env=mode,
            app_name=os.getenv("APP_NAME", "Nanvi AI Enterprise Assistant"),
            debug=False if mode == "production" else boolean("DEBUG", mode == "development"),
            oidc_issuer_url=os.getenv("OIDC_ISSUER_URL", "").rstrip("/"),
            oidc_client_id=os.getenv("OIDC_CLIENT_ID", ""),
            oidc_client_secret=os.getenv("OIDC_CLIENT_SECRET", ""),
            oidc_redirect_uri=os.getenv("OIDC_REDIRECT_URI", ""),
            oidc_jwks_url=os.getenv("OIDC_JWKS_URL", ""),
            oidc_audience=os.getenv("OIDC_AUDIENCE", ""),
            oidc_algorithms=tuple(x.strip() for x in os.getenv("OIDC_ALGORITHMS", "RS256").split(",") if x.strip()),
            company_file_roots=_parse_company_roots(os.getenv("COMPANY_FILE_ROOTS", "")),
            company_file_max_size_bytes=integer("COMPANY_FILE_MAX_SIZE_BYTES", 10 * 1024 * 1024),
            database_url=_sanitize_database_url(os.getenv("DATABASE_URL", "")),
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
            hsts_enabled=True if mode == "production" else boolean("HSTS_ENABLED", False),
            llm_provider=os.getenv("LLM_PROVIDER", "groq").strip().lower(),
            llm_model=os.getenv("LLM_MODEL", "llama-3.3-70b-versatile").strip(),
            groq_api_key=os.getenv("GROQ_API_KEY", ""),
            jwt_secret=os.getenv("JWT_SECRET", ""),
            demo_auth_enabled=boolean("DEMO_AUTH_ENABLED", False),
            local_auth_enabled=boolean("LOCAL_AUTH_ENABLED", True),
            local_auth_db_path=os.getenv("LOCAL_AUTH_DB_PATH", "").strip(),
            local_auth_tenant_id=os.getenv("LOCAL_AUTH_TENANT_ID", "enterprise-tenant").strip() or "enterprise-tenant",
            google_client_id=os.getenv("GOOGLE_CLIENT_ID", "").strip(),
            google_client_secret=os.getenv("GOOGLE_CLIENT_SECRET", "").strip(),
            google_redirect_uri=os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:5173").strip(),
            gmail_refresh_token=os.getenv("GMAIL_REFRESH_TOKEN", "").strip(),
            gmail_access_token=os.getenv("GMAIL_ACCESS_TOKEN", "").strip(),
            tavily_api_key=os.getenv("TAVILY_API_KEY", "").strip(),
            supabase_url=os.getenv("SUPABASE_URL", "").strip(),
            supabase_key=os.getenv("SUPABASE_KEY", "").strip(),
            supabase_database_url=_sanitize_database_url(os.getenv("SUPABASE_DATABASE_URL", "")),
            retrieval_v2_enabled=boolean("RETRIEVAL_V2_ENABLED", True),
            groq_max_concurrency=integer("GROQ_MAX_CONCURRENCY", 3),
            groq_token_budget_ceiling=integer("GROQ_TOKEN_BUDGET_CEILING", 3500),
            groq_max_retries=integer("GROQ_MAX_RETRIES", 3),
            encryption_key=os.getenv("ENCRYPTION_KEY", "").strip(),
            encryption_key_id=os.getenv("ENCRYPTION_KEY_ID", "v1").strip(),
            allow_legacy_gmail_token=boolean("ALLOW_LEGACY_GMAIL_TOKEN", False),
            github_client_id=os.getenv("GITHUB_CLIENT_ID", "").strip(),
            github_client_secret=os.getenv("GITHUB_CLIENT_SECRET", "").strip(),
            oauth_redirect_base_url=os.getenv("OAUTH_REDIRECT_BASE_URL", "").strip().rstrip("/") or (origins[0] if origins else "http://localhost:5173"),
            rag_relevance_threshold=number("RAG_RELEVANCE_THRESHOLD", 25.0),
            openai_api_key=openai_api_key,
            realtime_voice_enabled=boolean("REALTIME_VOICE_ENABLED", bool(openai_api_key)),
            realtime_voice_model=os.getenv("REALTIME_VOICE_MODEL", "gpt-live-1").strip(),
        )


def _sanitize_database_url(url: str) -> str:
    url = url.strip()
    if not url:
        return ""
    import urllib.parse
    import re
    match = re.match(r"^(postgres(?:ql)?://)([^:]+):(.*)@([^@]+)$", url)
    if match:
        scheme, user, password_raw, host_and_rest = match.groups()
        if any(c in password_raw for c in "+?#") or ("%" in password_raw and not re.search(r"%[0-9a-fA-F]{2}", password_raw)):
            encoded_pw = urllib.parse.quote_plus(password_raw)
            return f"{scheme}{user}:{encoded_pw}@{host_and_rest}"
    return url


def _parse_company_roots(value: str) -> tuple[tuple[str, str], ...]:
    if not value.strip():
        return tuple()
    entries = []
    for item in value.split(";"):
        if "=" not in item:
            raise ValueError("COMPANY_FILE_ROOTS entries must be Name=Path")
        name, path = (x.strip() for x in item.split("=", 1))
        if not name or not path:
            raise ValueError("COMPANY_FILE_ROOTS entries must include a name and path")
        entries.append((name, path))
    return tuple(entries)


settings = Settings.from_env()
