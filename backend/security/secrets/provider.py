from __future__ import annotations

from abc import ABC, abstractmethod


class SecretNotFoundError(KeyError):
    """Raised when a required secret cannot be resolved."""


class SecretProvider(ABC):
    """Provider-independent interface for retrieving application secrets."""

    @abstractmethod
    def get_secret(self, name: str) -> str:
        """Return a secret value or raise SecretNotFoundError."""
        raise NotImplementedError
