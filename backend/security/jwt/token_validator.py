from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class TokenClaims:
    subject: str
    issuer: str
    audience: str | list[str] | None
    expires_at: int
    claims: dict[str, Any]


class TokenValidator(ABC):
    """Provider-independent JWT validation contract."""

    @abstractmethod
    def validate(self, token: str) -> TokenClaims:
        raise NotImplementedError
