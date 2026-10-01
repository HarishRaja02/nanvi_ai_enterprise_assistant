# Authentication

## Implemented

The backend authenticates protected API requests with `Authorization: Bearer <JWT>`.

`backend/security/token_validator.py`:
- requires a token shaped like a JWT;
- reads the untrusted header only to select a configured algorithm/key ID;
- restricts algorithms to `OIDC_ALGORITHMS` (default `RS256`);
- retrieves and caches JWKS for one hour;
- refreshes JWKS once when a key ID is missing;
- verifies signature, issuer, audience and required `exp`, `iat`, `sub`, `iss` claims;
- maps supported `roles`, tenant and department claims into `UserIdentity`.

`get_current_user` rejects missing/non-bearer/invalid tokens with HTTP 401 and never logs the token.

## Current API

- `GET /api/auth/me` — protected identity endpoint.

## Partially implemented

`AuthenticationService` can generate a random login state and construct an authorization URL through `OIDCIdentityProvider`, but the FastAPI application does not expose an authorization start route, callback, authorization-code exchange, PKCE implementation, refresh-token lifecycle or server-side browser session.

The frontend can redirect to `VITE_SSO_LOGIN_URL` and has `VITE_DEMO_MODE` for development.

## Planned/Future

Implement and independently security-review the complete OIDC authorization-code + PKCE/session lifecycle before using browser SSO as a production feature. Do not infer that the current `login_url()` method constitutes a complete login system.

## Secrets

`OIDC_CLIENT_SECRET` is configuration only and must be supplied by an approved secret manager in production. It is not part of `UserIdentity` or graph state.
