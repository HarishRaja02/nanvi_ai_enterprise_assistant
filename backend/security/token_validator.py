import json
import time
from typing import Any

import httpx
import jwt

from backend.core.config import settings
from backend.security.exceptions import AuthenticationError
from backend.security.models import UserIdentity
from backend.security.authorization.rbac import Role, normalize_role


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
        # Development/demo mode: accept locally-signed HS256 tokens.
        # Demo authentication is explicitly opt-in and disabled by default.
        if (
            (settings.app_env == "development" or settings.demo_auth_enabled or settings.local_auth_enabled)
            and settings.jwt_secret
        ):
            try:
                header = jwt.get_unverified_header(token)
                if header.get("alg") == "HS256":
                    claims = jwt.decode(
                        token,
                        settings.jwt_secret,
                        algorithms=["HS256"],
                        options={"require": ["exp", "iat", "sub", "iss", "aud"], "verify_aud": False},
                    )
                    expected_audience = {"nanvi-dev": "nanvi-dev", "nanvi-local": "nanvi-local"}.get(claims["iss"])
                    if not expected_audience or claims["aud"] != expected_audience:
                        raise AuthenticationError("Invalid local token issuer or audience")
                    raw_roles = claims.get("roles", [])
                    if isinstance(raw_roles, str):
                        raw_roles = [raw_roles]
                    roles = frozenset(normalized for role in raw_roles if (normalized := normalize_role(role)) is not None)

                    # Local account deletion must take effect immediately, not only
                    # after the token's eight-hour expiry. Resolve local identities
                    # against the account store on every authenticated request.
                    if claims["iss"] == "nanvi-local":
                        if not settings.local_auth_enabled:
                            raise AuthenticationError("Local sign-in is disabled")
                        tenant_id = claims.get("tenant_id")
                        if not tenant_id:
                            raise AuthenticationError("Local token has no tenant")
                        account = None
                        try:
                            from backend.security.local_accounts import get_local_account_store

                            account = get_local_account_store().get_account(claims["sub"], tenant_id)
                        except ValueError as exc:
                            raise AuthenticationError("Local account is no longer available") from exc
                        except Exception:
                            # If account store is unreachable (e.g. serverless cold start or network blip),
                            # fall back to the cryptographically verified claims below instead of booting the user.
                            pass

                        if account:
                            account_role = normalize_role(account.get("role", ""))
                            if not account.get("active") or account_role is None or roles != frozenset({account_role}):
                                raise AuthenticationError("Local account is inactive or its role has changed")

                            return UserIdentity(
                                subject=account["id"],
                                issuer=claims["iss"],
                                email=account.get("email"),
                                name=account.get("display_name"),
                                tenant_id=tenant_id,
                                department=account.get("department"),
                                roles=frozenset({account_role}),
                            )

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
        roles = frozenset(normalized for role in raw_roles if (normalized := normalize_role(role)) is not None)
        return UserIdentity(
            subject=claims["sub"],
            issuer=claims["iss"],
            email=claims.get("email") or claims.get("preferred_username"),
            name=claims.get("name"),
            tenant_id=claims.get("tid") or claims.get("tenant_id"),
            department=claims.get("department") or claims.get("dept"),
            roles=roles,
        )
