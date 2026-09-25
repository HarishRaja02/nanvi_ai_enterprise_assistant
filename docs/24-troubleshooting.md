# Troubleshooting Guide

## Backend will not start

### `COMPANY_FILE_ROOTS` configuration error
In production, configure exactly `Customers`, `Finance`, `HR`, `Projects`, `Contracts` in `Name=Path` form.

### PostgreSQL support unavailable
The PostgreSQL repository requires `psycopg[binary,pool]` from `requirements.txt`. A live PostgreSQL server is still required for real database execution.

### LangGraph missing
Install the pinned runtime dependencies. The orchestrator intentionally raises a clear error if LangGraph cannot be imported.

## HTTP 401

Check:
- `Authorization: Bearer <token>` exists;
- issuer/audience match configuration;
- token is unexpired;
- token signing key is present in JWKS;
- algorithm is allowed.

Do not paste tokens into logs or tickets.

## HTTP 403

The authenticated identity may be missing tenant/role context. Check token role/tenant/department claims and central policy rules.

## HTTP 503 on chat

The default `get_chat_service()` dependency intentionally returns `503 Chat service is not configured`. A composition layer must inject a configured `ChatService`.

## HTTP 502 on chat

The route maps orchestration runtime failures to a generic safe 502. Inspect correlated server logs/audit events using request/correlation/trace IDs.

## Email failures

- Check delegated token presence and `Mail.Read` scope.
- Verify user/tenant match.
- Inspect `external_api_failed`/`external_email_api_failed` events.
- 429 means provider rate limiting; respect `Retry-After`.

## Retrieval returns nothing

Check source authorization metadata first. If vector search fails, keyword fallback should be recorded. A restricted result being absent can be the correct security behavior.

## Report download fails

The report ID must belong to the authenticated user/tenant and the temporary token must be valid, unexpired and unused.

## Frontend commands say package not found

Run `npm install` from `frontend/`. The repository intentionally does not include `node_modules`.

## Docker commands unavailable

Install Docker/BuildKit or use the CI environment. Static Docker configuration tests can still run through `pytest`.

## Status classification

### Implemented
The troubleshooting steps above correspond to current code paths and configuration errors.

### Partially implemented
Several troubleshooting cases depend on infrastructure that is represented by interfaces or deployment examples rather than running locally.

### Planned/Future
Deployment-specific operational diagnostics should be added when the production platform is selected.
