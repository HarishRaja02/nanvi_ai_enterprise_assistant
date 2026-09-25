import json
import time
from typing import Any

import httpx
import jwt

from backend.core.config import settings
from backend.security.exceptions import AuthenticationError
from backend.security.models import UserIdentity
from backend.security.authorization.rbac import Role


class TokenValidator:
    """Validates OIDC JWT access tokens using the provider's JWKS endpoint."""

    def __init__(self, jwks_url: str | None = None, issuer: str | None = None, audience: str | None = None) -> None:
        self.jwks_url = jwks_url or settings.oidc_jwks_url
        self.issuer = issuer or settings.oidc_issuer_url
        self.audience = audience or settings.oidc_audience
        self.algorithms = settings.oidc_algorithms
        self._jwks: dict[str, Any] | None = None
        self._jwks_loaded_at = 0.0
        self._jwks_ttl_seconds = 3600

    def _load_jwks(self) -> dict[str, Any]:
        if self._jwks and time.time() - self._jwks_loaded_at < self._jwks_ttl_seconds:
            return self._jwks
        if not self.jwks_url:
            raise AuthenticationError("OIDC JWKS URL is not configured")
        try:
            response = httpx.get(self.jwks_url, timeout=5.0)
            response.raise_for_status()
            data = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise AuthenticationError("Unable to retrieve identity-provider signing keys") from exc
        if not isinstance(data, dict) or not isinstance(data.get("keys"), list):
            raise AuthenticationError("Invalid JWKS response")
        self._jwks = data
        self._jwks_loaded_at = time.time()
        return data

    def validate(self, token: str) -> UserIdentity:
        if not token or token.count(".") != 2:
            raise AuthenticationError("Malformed access token")

        # Development-mode: accept locally-signed HS256 tokens
        if settings.app_env == "development" and settings.jwt_secret:
            try:
                header = jwt.get_unverified_header(token)
                if header.get("alg") == "HS256":
                    claims = jwt.decode(
                        token,
                        settings.jwt_secret,
                        algorithms=["HS256"],
                        issuer="nanvi-dev",
                        audience="nanvi-dev",
                        options={"require": ["exp", "iat", "sub", "iss"]},
                    )
                    raw_roles = claims.get("roles", [])
                    if isinstance(raw_roles, str):
                        raw_roles = [raw_roles]
                    roles = frozenset(Role(role) for role in raw_roles if role in {r.value for r in Role})
                    return UserIdentity(
                        subject=claims["sub"],
                        issuer=claims["iss"],
                        email=claims.get("email"),
                        name=claims.get("name"),
                        tenant_id=claims.get("tenant_id"),
                        department=claims.get("department"),
                        roles=roles,
                    )
            except (jwt.InvalidTokenError, ValueError, TypeError, KeyError):
                pass  # Fall through to OIDC validation

        try:
            header = jwt.get_unverified_header(token)
            algorithm = header.get("alg")
            kid = header.get("kid")
            if algorithm not in self.algorithms or not kid:
                raise AuthenticationError("Unsupported access-token header")

            key_data = next((key for key in self._load_jwks()["keys"] if key.get("kid") == kid), None)
            if not key_data:
                # Refresh once so key rotation is handled without trusting a stale cache.
                self._jwks = None
                key_data = next((key for key in self._load_jwks()["keys"] if key.get("kid") == kid), None)
            if not key_data:
                raise AuthenticationError("Signing key not found")

            public_key = jwt.algorithms.RSAAlgorithm.from_jwk(json.dumps(key_data))
            claims = jwt.decode(
                token,
                key=public_key,
                algorithms=list(self.algorithms),
                issuer=self.issuer,
                audience=self.audience,
                options={"require": ["exp", "iat", "sub", "iss"]},
            )
        except AuthenticationError:
            raise
        except (jwt.InvalidTokenError, ValueError, TypeError) as exc:
            raise AuthenticationError("Invalid access token") from exc

        raw_roles = claims.get("roles", [])
        if isinstance(raw_roles, str):
            raw_roles = [raw_roles]
        roles = frozenset(Role(role) for role in raw_roles if role in {r.value for r in Role})
        return UserIdentity(
            subject=claims["sub"],
            issuer=claims["iss"],
            email=claims.get("email") or claims.get("preferred_username"),
            name=claims.get("name"),
            tenant_id=claims.get("tid") or claims.get("tenant_id"),
            department=claims.get("department") or claims.get("dept"),
            roles=roles,
        )
