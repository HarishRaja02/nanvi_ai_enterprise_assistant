# Nanvi Production Hardening & Deployment Architecture

## Status

This document describes production hardening of the existing Nanvi architecture. It does not claim production readiness by itself. Enterprise infrastructure, identity configuration, security review, penetration testing, and operational acceptance remain required.

## Deployment architecture

```text
Internet
  |
  v
Managed WAF / Load Balancer / TLS
  |
  +--------------------+
  |                    |
  v                    v
React static app      FastAPI API
(Nginx/CDN)              |
                         +--> Entra ID / OIDC
                         +--> PostgreSQL (private subnet)
                         +--> Redis (private subnet)
                         +--> Object/document storage
                         +--> Microsoft Graph
                         +--> OpenTelemetry Collector
                                      |
                                      v
                                  SIEM / APM
```

### Security boundaries

1. Browser is untrusted.
2. FastAPI is the application trust boundary.
3. LLM is never an authorization boundary.
4. Tool execution requires authentication, authorization, policy, validation and audit.
5. PostgreSQL and Redis are private-network services.
6. Secrets are injected at runtime from an enterprise secret manager.
7. Documents/emails/web content are untrusted data.

## Development

Use local PostgreSQL/Redis with `deploy/docker/docker-compose.dev.yml`.

- Debug may be enabled.
- No production secrets.
- No HSTS.
- CORS may allow localhost.
- In-memory rate limiter/queues are acceptable.
- In-memory audit sink is acceptable for tests/local development.
- Local filesystem may be used for approved test data.

Never connect development to real company production data.

## Testing

Testing must be isolated from production and use dedicated:

- database
- Redis DB/instance
- filesystem root
- identity tenant/application registration
- test secrets

Run:

```text
pytest -q
pip-audit
npm audit --audit-level=high
npm run build
```

Security tests must include authorization bypass, tenant isolation, prompt injection, indirect injection, SQL injection, path traversal, SSRF, tool abuse, report access, rate limits and malformed uploads.

## Production

Production configuration must:

- set `APP_ENV=production`
- set `DEBUG=false`
- use private PostgreSQL
- use distributed Redis
- use managed/enterprise secret storage
- use TLS everywhere
- restrict CORS to the exact frontend origin
- enable HSTS only behind HTTPS
- enable OpenTelemetry
- use durable audit storage/SIEM
- use a distributed rate limiter
- use centralized object/document storage
- disable local development stores
- use locked dependencies
- run vulnerability scanning in CI

## Secrets

`.env` files are for local development only. Production secrets must come from an enterprise secret manager such as Azure Key Vault, AWS Secrets Manager, HashiCorp Vault, or an equivalent approved platform.

Never put:

- OAuth client secrets
- database passwords
- Redis credentials
- signing keys
- API keys
- access tokens

into the React bundle or source repository.

## HTTPS / reverse proxy

Terminate TLS at the enterprise ingress/load balancer or hardened Nginx. FastAPI should normally remain private behind the proxy.

Required controls:

- TLS 1.2+
- HTTP to HTTPS redirect
- HSTS in production
- secure forwarding headers
- request size limits
- upstream timeouts
- WAF rules where approved

## PostgreSQL

Use a dedicated application account with the minimum required privileges. The AI never receives credentials.

Recommended production controls:

- private network only
- TLS to database where required
- separate migration account
- read-only application account for AI query paths
- connection pooling
- statement timeout
- result limits
- backups + restore tests
- PostgreSQL Row Level Security where it materially strengthens tenant isolation

## Migrations

Use a versioned migration system (Alembic or an enterprise-approved equivalent) executed as a controlled deployment step. Application containers should not silently create/alter production schemas at startup.

Migration process:

```text
Build -> migration validation -> backup/checkpoint -> migrate -> health check -> deploy
```

Rollback must be designed per migration; destructive down-migrations should not be assumed safe.

## Redis / background jobs

Redis is appropriate for distributed rate limiting and background job coordination, but it must be private and authenticated.

Long-running work such as document parsing, indexing, report generation and expensive analysis should move to background workers.

Worker requirements:

- idempotent jobs
- retry limits
- dead-letter handling
- visibility/lease timeout
- job audit events
- payload minimization
- no secrets in job payloads

## Logging and monitoring

Separate:

- application logs
- security audit logs
- access logs
- metrics
- traces

Do not log passwords, access tokens, OAuth tokens, SQL parameters, email bodies or raw document contents.

OpenTelemetry should provide request/tool/database/job traces. The OTEL collector should forward telemetry to the approved enterprise observability platform.

## Health checks

`/api/health/live` should only indicate that the process is alive.

`/api/health/ready` should validate required dependencies once real database/Redis clients are application-managed.

Do not expose detailed dependency failure information publicly.

## Backups / disaster recovery

Enterprise infrastructure must provide:

- encrypted PostgreSQL backups
- encrypted document/report storage backups
- defined retention
- tested restore procedure
- RPO/RTO targets
- separate backup credentials
- geographically appropriate recovery strategy
- periodic disaster-recovery exercises

A backup that has never been restored successfully should not be considered a verified backup.

## CI/CD

Required gates:

1. unit tests
2. security tests
3. integration tests
4. frontend build
5. dependency vulnerability scan
6. container image scan
7. secret scanning
8. SBOM generation
9. migration validation
10. deployment health checks

Production deployment should use immutable versioned images.

## Enterprise infrastructure still required

The codebase cannot provide these by itself:

- Microsoft Entra tenant/application configuration
- enterprise secret manager
- managed TLS certificates
- WAF/load balancer
- managed PostgreSQL HA
- managed Redis HA
- centralized object storage
- SIEM
- APM/OTEL collector
- backup platform
- disaster-recovery environment
- container registry
- image vulnerability scanner
- enterprise network/firewall policies

## Human security review still required

Before production approval, security/architecture owners should review:

- OAuth redirect URIs and scopes
- tenant isolation model
- database privileges
- file/document trust model
- prompt-injection controls
- SSRF policy
- DLP/PII classification
- report-download authorization
- incident response
- backup/DR
- threat model
- penetration-test results
- dependency exceptions

No code change can substitute for these organizational controls.
