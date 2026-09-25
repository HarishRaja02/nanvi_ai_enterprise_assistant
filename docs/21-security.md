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

### Secret protection
The code does not intentionally place passwords, API keys, OAuth tokens or DB credentials in agent state, prompts, logs or frontend source. Structured logging recursively scrubs sensitive key names and common bearer/secret assignment patterns.

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
