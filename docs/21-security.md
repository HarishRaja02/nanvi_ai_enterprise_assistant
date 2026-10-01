# Security

## Implemented controls

### Identity and authorization
- JWT/JWKS validation with issuer/audience/algorithm/required claims.
- Central RBAC + ABAC.
- Tenant isolation.
- Resource ownership/restricted-department rules.
- Backend authorization independent of frontend visibility and AI decisions.

### Input/data protection
- Typed API validation.
- SQL tokenizer/validator and read-only database boundary.
- Filesystem traversal/absolute/UNC/symlink/type/size controls.
- OOXML archive safety checks.
- SSRF validation helper.
- Prompt-injection heuristic and untrusted-content envelopes.
- Tool allowlist, budget, timeout and output filtering.

### Secret protection & classification
Secrets within the Nanvi platform are strictly categorized to prevent credential leakage and ensure rigorous hygiene:
- **Production Secrets**: (API keys, database DSNs, JWT secret, master encryption key). Must NEVER be checked into source control or committed in configuration files. Provided exclusively via container environment variables or managed secrets stores (AWS Secrets Manager, GCP Secret Manager, Vault).
- **Synthetic Test Secrets**: Controlled test fixtures used inside automated test suites (e.g., `tests/`), clearly marked with mock/test prefixes.
- **Demo Credentials**: Used exclusively when `APP_MODE=development` or `demo`. Explicitly forbidden and blocked by fail-fast startup checks when `APP_MODE=production`.
- **Provider Tokens**: Per-user and per-tenant third-party tokens (Google, GitHub OAuth). Always encrypted at rest using AES-GCM via `ConnectionManager` with rotating key IDs.
- **Placeholders**: Sanitized templates only, maintained in `.env.example`.

Automated repository secret scanning via Gitleaks runs in CI on every push and pull request with full history scanning (`fetch-depth: 0`) to fail builds if any credentials are introduced. See `docs/SECRETS_ROTATION.md` for revocation and rotation procedures.
Structured logging recursively scrubs sensitive key names and bearer/secret patterns.


### Transport/browser controls
Security headers include CSP, `X-Content-Type-Options`, `X-Frame-Options`, Referrer-Policy, Permissions-Policy and optional HSTS. Production reverse-proxy examples require TLS.

## Audit

Audit records include event type, outcome, actor, tenant, resource, timestamp, request/correlation/trace IDs and sanitized metadata. This is sufficient for investigation while avoiding raw secrets and large business payloads.

## Partially implemented

- In-memory audit sink is the current application implementation; durable SIEM/audit storage is not included.
- Encryption is an interface, not a production cryptographic provider.
- Authentication browser flow is incomplete.
- SSRF protection does not eliminate DNS-rebinding races by itself.
- Tool timeout cannot forcibly terminate arbitrary Python threads.
- No file-upload malware/sandbox pipeline exists.

## Planned/Future

Use managed secret/key services, durable audit/SIEM, production identity/session flow, WAF/network controls, vulnerability scanning and staging security testing.
