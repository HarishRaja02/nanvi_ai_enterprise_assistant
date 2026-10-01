from __future__ import annotations

from backend.security.secrets.provider import SecretProvider


class SecretsService:
    """Security-layer facade. Application code depends on this, not a vendor."""

    def __init__(self, provider: SecretProvider) -> None:
        self._provider = provider

    def get(self, name: str) -> str:
        return self._provider.get_secret(name)
