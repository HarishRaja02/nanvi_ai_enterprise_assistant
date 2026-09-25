# Environment Configuration

## Implemented settings

The backend reads environment variables through `backend/core/config.py`.

### Application
- `APP_ENV`: development, testing or production.
- `DEBUG`
- `LOG_LEVEL`
- `REQUEST_TIMEOUT_SECONDS`

### OIDC
- `OIDC_ISSUER_URL`
- `OIDC_CLIENT_ID`
- `OIDC_CLIENT_SECRET`
- `OIDC_REDIRECT_URI`
- `OIDC_JWKS_URL`
- `OIDC_AUDIENCE`
- `OIDC_ALGORITHMS` (default `RS256`)

### Database
- `DATABASE_URL`
- `DATABASE_POOL_MIN_SIZE`
- `DATABASE_POOL_MAX_SIZE`
- `DATABASE_STATEMENT_TIMEOUT_MS`

### Redis/rate limiting
- `REDIS_URL`
- `RATE_LIMIT_REQUESTS`
- `RATE_LIMIT_WINDOW_SECONDS`

### Files
- `COMPANY_FILE_ROOTS`
- `COMPANY_FILE_MAX_SIZE_BYTES` (default 10 MiB)

Production `COMPANY_FILE_ROOTS` must explicitly contain exactly Customers, Finance, HR, Projects and Contracts.

### Observability / browser security
- `OTEL_ENABLED`
- `OTEL_SERVICE_NAME`
- `OTEL_EXPORTER_OTLP_ENDPOINT`
- `CORS_ORIGINS`
- `HSTS_ENABLED`

## Frontend settings

- `VITE_DEMO_MODE`
- `VITE_SSO_LOGIN_URL`

Do not put server secrets in Vite variables. Vite variables are browser-visible.

## Secret handling

Environment examples contain placeholders only. Local passwords must be supplied by the developer and must not be committed. Production secret values must come from an approved secret manager. The DR utility explicitly excludes secret-like configuration from its backup fixture.

## Partially implemented

`EnvironmentSecretProvider` is a development/local provider. A managed Vault/Key Vault/Secrets Manager adapter is not included. The encryption module is an abstraction with no fake cryptographic implementation.

## Planned/Future

Use enterprise secret and key management in production and remove placeholder values from deployment configuration.
