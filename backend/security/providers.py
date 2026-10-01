from abc import ABC, abstractmethod
from urllib.parse import urlencode

from backend.core.config import settings


class IdentityProvider(ABC):
    """Provider-independent identity-provider contract."""

    @abstractmethod
    def authorization_url(self, state: str) -> str:
        raise NotImplementedError


class OIDCIdentityProvider(IdentityProvider):
    """Generic OIDC authorization endpoint adapter.

    It is intentionally provider-neutral and can be configured for Microsoft
    Entra ID or another standards-compliant OIDC provider.
    """

    def __init__(self, authorization_endpoint: str, scopes: tuple[str, ...] = ("openid", "profile", "email")) -> None:
        self.authorization_endpoint = authorization_endpoint
        self.scopes = scopes

    def authorization_url(self, state: str) -> str:
        if not settings.oidc_client_id or not settings.oidc_redirect_uri:
            raise ValueError("OIDC_CLIENT_ID and OIDC_REDIRECT_URI must be configured")

        query = urlencode(
            {
                "client_id": settings.oidc_client_id,
                "response_type": "code",
                "redirect_uri": settings.oidc_redirect_uri,
                "scope": " ".join(self.scopes),
                "state": state,
            }
        )
        return f"{self.authorization_endpoint}?{query}"
