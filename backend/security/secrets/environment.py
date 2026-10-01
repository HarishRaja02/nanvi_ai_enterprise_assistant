from __future__ import annotations

import os

from backend.security.secrets.provider import SecretNotFoundError, SecretProvider


class EnvironmentSecretProvider(SecretProvider):
    """Development/local provider backed by process environment variables.

    Production applications should replace this implementation with a managed
    secret provider such as Vault, Azure Key Vault, or AWS Secrets Manager.
    """

    def get_secret(self, name: str) -> str:
        value = os.getenv(name)
        if value is None or value == "":
            raise SecretNotFoundError(f"Secret '{name}' is not configured")
        return value
