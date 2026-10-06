"""Configuration settings for UECP integration."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv

# Ensure environment is loaded
_env_path = Path(__file__).resolve().parent.parent.parent / ".env"
load_dotenv(_env_path, override=False)


@dataclass(frozen=True)
class UECPConfig:
    enabled: bool
    base_url: str
    application_id: str
    application_key: str
    credential_id: str
    credential_secret: str
    validation_timeout_seconds: float = 5.0
    cache_ttl_seconds: int = 60
    allow_insecure_http: bool = False

    def __repr__(self) -> str:
        # Strictly mask secrets in string/repr representations
        return (
            f"UECPConfig(enabled={self.enabled}, "
            f"base_url='{self.base_url}', "
            f"application_id='{self.application_id}', "
            f"application_key='[MASKED]', "
            f"credential_id='{self.credential_id}', "
            f"credential_secret='[MASKED]', "
            f"validation_timeout_seconds={self.validation_timeout_seconds}, "
            f"cache_ttl_seconds={self.cache_ttl_seconds})"
        )

    def validate_configuration(self, is_production: bool = False) -> list[str]:
        """Validate UECP settings against security constraints."""
        errors: list[str] = []
        if not self.enabled:
            if is_production:
                errors.append("UECP_ENABLED cannot be false in production (fail-closed)")
            return errors

        if not self.base_url:
            errors.append("UECP_BASE_URL must be configured")
        elif not self.allow_insecure_http and not self.base_url.startswith("https://"):
            errors.append("UECP_BASE_URL must use HTTPS protocol")

        if not self.application_id:
            errors.append("UECP_APPLICATION_ID must be configured")
        if not self.credential_id:
            errors.append("UECP_CREDENTIAL_ID must be configured")
        if not self.credential_secret:
            errors.append("UECP_CREDENTIAL_SECRET must be configured")

        if self.validation_timeout_seconds <= 0:
            errors.append("UECP_VALIDATION_TIMEOUT_SECONDS must be positive")
        if self.cache_ttl_seconds <= 0 or self.cache_ttl_seconds > 300:
            errors.append("UECP_CACHE_TTL_SECONDS must be between 1 and 300 seconds")

        return errors

    @classmethod
    def from_env(cls) -> "UECPConfig":
        def boolean(name: str, default: bool) -> bool:
            return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}

        def number(name: str, default: float) -> float:
            try:
                v = float(os.getenv(name, str(default)))
                return v if v > 0 else default
            except ValueError:
                return default

        def integer(name: str, default: int) -> int:
            try:
                v = int(os.getenv(name, str(default)))
                return v if v > 0 else default
            except ValueError:
                return default

        raw_enabled = os.getenv("UECP_ENABLED")
        # In production default enabled=True. If explicitly unset in dev, enabled=False
        app_mode = os.getenv("APP_MODE", os.getenv("APP_ENV", "production")).strip().lower()
        is_prod = app_mode == "production"

        if raw_enabled is not None:
            enabled = raw_enabled.strip().lower() in {"1", "true", "yes", "on"}
        else:
            # If UECP_BASE_URL is present, treat as enabled, else enabled in prod
            enabled = is_prod or bool(os.getenv("UECP_BASE_URL"))

        base_url = os.getenv("UECP_BASE_URL", "").strip().rstrip("/")
        app_id = os.getenv("UECP_APPLICATION_ID", "").strip()
        app_key = os.getenv("UECP_APPLICATION_KEY", "").strip()
        cred_id = os.getenv("UECP_CREDENTIAL_ID", "").strip()
        cred_secret = os.getenv("UECP_CREDENTIAL_SECRET", "").strip()

        timeout = number("UECP_VALIDATION_TIMEOUT_SECONDS", 5.0)
        cache_ttl = integer("UECP_CACHE_TTL_SECONDS", 60)
        allow_http = boolean("UECP_ALLOW_INSECURE_HTTP", False)

        return cls(
            enabled=enabled,
            base_url=base_url,
            application_id=app_id,
            application_key=app_key,
            credential_id=cred_id,
            credential_secret=cred_secret,
            validation_timeout_seconds=timeout,
            cache_ttl_seconds=cache_ttl,
            allow_insecure_http=allow_http,
        )


_config_instance: UECPConfig | None = None


def get_uecp_config() -> UECPConfig:
    global _config_instance
    if _config_instance is None:
        _config_instance = UECPConfig.from_env()
    return _config_instance


def set_uecp_config(config: UECPConfig | None) -> None:
    global _config_instance
    _config_instance = config
