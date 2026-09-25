import secrets

from backend.security.models import UserIdentity
from backend.security.providers import IdentityProvider
from backend.security.token_validator import TokenValidator


class AuthenticationService:
    """Application-level authentication service independent of any IdP."""

    def __init__(self, token_validator: TokenValidator, identity_provider: IdentityProvider) -> None:
        self.token_validator = token_validator
        self.identity_provider = identity_provider

    def create_login_state(self) -> str:
        return secrets.token_urlsafe(32)

    def login_url(self, state: str | None = None) -> str:
        return self.identity_provider.authorization_url(state or self.create_login_state())

    def authenticate_access_token(self, token: str) -> UserIdentity:
        return self.token_validator.validate(token)
