# Nanvi AI Enterprise Assistant — Final Handover

**Release state:** Final project freeze / Release Candidate
**Validation date:** 2026-09-18
**Scope:** Handover documentation and final verification only. No application functionality or architecture was added or redesigned during this handover.

## 1. Project overview

Nanvi AI Enterprise Assistant is a production-oriented enterprise AI assistant architecture for authenticated company users to ask questions over authorized company knowledge, structured data, email and files, perform controlled analysis, and generate reports with source transparency.

**Current status:** NOT READY for production certification. The repository contains a substantial validated application/security foundation, but the default runtime composition and several infrastructure-dependent integrations remain incomplete.

Implemented and validated areas include authentication/token validation, RBAC/ABAC, protected file access, controlled read-only SQL, read-only Microsoft Graph email integration, authorization-aware RAG, deterministic data analysis, report generation, source references, audit/observability, failure handling and a 273-test backend regression suite.

Not implemented or not fully wired include the complete browser OIDC/PKCE lifecycle, default production ChatService composition, concrete default Knowledge/Email/Data Analysis/Report agent wiring, email sending, file-upload API, streaming chat, durable production stores and live enterprise-provider certification.

Voice/avatar capabilities are **not implemented** and are not part of this frozen release candidate.

## 2. Architecture

Target architecture:

`React/TypeScript → WAF/LB → Nginx → FastAPI → Entra/OIDC → RBAC/ABAC → LangGraph → Tool Gateway → data connectors`

The LLM is not the security boundary. Backend authentication, authorization and connector/service controls are authoritative.

## 3. Technology stack

- Frontend: React 19, TypeScript 5.7, Vite 6, Vitest 2, ESLint 9.
- Backend: Python 3.11+, FastAPI 0.128, Pydantic 2.13, Uvicorn 0.48.
- AI orchestration: LangGraph 1.2.11.
- Authentication: JWT/JWKS validation, OIDC configuration, Microsoft Entra target deployment.
- Database: PostgreSQL via psycopg 3.2.10.
- Cache/queue infrastructure: Redis 8 client and Redis-oriented rate limiting/job queue components.
- Documents: pypdf, python-docx, openpyxl, python-pptx, reportlab.
- HTTP: httpx.
- Observability: OpenTelemetry APIs/exporter plus structured JSON logging.
- Security utilities: cryptography, PyYAML.

All backend requirement versions are exact-pinned in `requirements.txt` and mirrored in `pyproject.toml`.

## 4. Repository structure

```text
backend/                 FastAPI application and domain/integration modules
config/environments/     environment examples
 deploy/docker/           backend/frontend Dockerfiles and Compose examples
 deploy/nginx/            frontend and reverse-proxy configuration
 docs/                    implementation-based technical documentation
 frontend/                React/TypeScript/Vite application
 scripts/                 validation/DR/UAT utilities
tests/                   backend/security/integration/regression suites
requirements.txt         exact backend dependency set
pyproject.toml           Python package/build metadata
.env.example             non-secret environment template
HANDOVER.md              this handover document
```

## 5. Environment configuration

Use `.env.example` as the local template and `config/environments/*.env.example` as environment-specific examples. Never commit actual credentials.

Production requires explicit company roots for Customers, Finance, HR, Projects and Contracts. Production should use an approved secret manager for database, identity, Redis and provider secrets.

## 6. Authentication

JWT/JWKS validation verifies issuer, audience, expiration, issued-at, subject and approved algorithms. The security boundary is backend authentication rather than the frontend or LLM.

**Partial:** complete browser authorization-code exchange, PKCE, callback, refresh/session lifecycle remains a release prerequisite for enterprise SSO.

## 7. Authorization

Authorization is enforced in backend services and connector boundaries. Authentication context includes subject, tenant, department and roles. Protected operations are not delegated to the LLM.

## 8. RBAC / ABAC

RBAC maps enterprise roles to permissions. ABAC adds tenant, department, ownership and restricted-resource constraints. Frontend role information is UX-only and is not authoritative.

## 9. AI orchestration

LangGraph provides orchestration and capability routing. Graph state is designed to exclude credentials and sensitive secrets.

**Partial:** the default orchestrator currently contains placeholder implementations for Knowledge, Email, Data Analysis and Report agents; production composition must inject concrete implementations.

## 10. Tool Gateway

The Secure Tool Gateway provides an execution boundary around tools: allowlist → authentication → authorization/policy → budget → execution → output validation → audit. Tool permissions are backend-controlled.

Known limitation: a Python thread timeout cannot forcibly terminate arbitrary already-running work.

## 11. Data connectors

Connector families:
- Local/company files.
- PostgreSQL.
- Microsoft Graph email.
- Retrieval/vector/keyword components.
- Report storage/generation.

Each protected connector has a service/repository boundary rather than direct LLM access.

## 12. RAG

RAG includes document chunking, embedding-provider abstraction, vector retrieval, keyword retrieval, reranking abstraction, authorization metadata and source references. Authorization occurs before protected results are exposed to the answer layer.

The controlled evaluation retrieved 10/10 relevant-source cases with zero permission-filter failures. Production semantic quality still requires staging validation with the selected embedding/vector infrastructure and live LLM.

## 13. SQL

SQL access is read-only, parameterized, allowlisted and row/result-size limited. Destructive statements, multi-statement execution, unauthorized tables and related injection paths are tested.

Production still requires a least-privilege PostgreSQL account plus appropriate views/RLS/field controls.

## 14. Email

Microsoft Graph integration is delegated and read-only in the frozen implementation. `Mail.Read` is checked and provider context is bound to the authenticated user/tenant. Email is treated as untrusted content for AI processing.

Email sending is not implemented.

## 15. File processing

Supported parsing includes PDF, Word, Excel, CSV, PowerPoint and text. Local access is confined to explicitly configured roots, with traversal, absolute/UNC/drive-path and symlink protections plus file-size and extension controls. OOXML archive safety checks are included.

File-upload HTTP API is not implemented.

## 16. Data analysis

Deterministic analysis supports aggregation/filtering/grouping/comparison/trend/basic statistics over authorized structured data. Analysis lineage carries source and access metadata.

## 17. Reports

Report generation supports Excel, PDF, Word and PowerPoint. Reports carry source lineage and are generated only after source authorization. Download authorization is separate from creation authorization.

Known limitation: current report storage is local/private and not a production HA storage service. Temporary download tokens are currently URL-based and require production logging/transport review.

## 18. Frontend

React/TypeScript/Vite provides authentication state handling, chat UI, conversation history, source display, report download and responsive/accessibility behavior.

Frontend authorization metadata is presentation-only. Backend authorization remains authoritative.

Actual clean frontend build was not certified in this environment because `node_modules` and a committed lockfile are absent and npm registry access was unavailable.

## 19. Backend

FastAPI exposes health, authentication identity, chat/history, source-reference and report-download routes. Services and repositories provide boundaries for connectors and security policies.

The default chat dependency currently returns 503 until application composition supplies a ChatService.

## 20. Database

PostgreSQL integration uses a read-only transaction and statement timeout with bounded rows/result size and explicit query validation. No automatic DDL is performed at FastAPI startup.

The current migrations module is a policy marker for external versioned migrations; no required application schema migration is included in this repository.

## 21. Redis / workers

Redis-backed rate limiting is intended for production. The job queue contains idempotent enqueue behavior and bounded retry semantics.

The complete production worker dequeue/ack/visibility-timeout/dead-letter lifecycle is not certified.

## 22. Logging

Structured JSON logging includes request/correlation/trace IDs and records authentication, authorization, tool, connector, worker and error events. Secrets/tokens are redacted and business payloads are not intended to be logged unnecessarily.

## 23. Monitoring

OpenTelemetry hooks, request timing, structured events and operational failure events are implemented. Enterprise SIEM/OTel collector, alerting and retention must be supplied by the deployment environment.

## 24. Security

Security controls include JWT/JWKS validation, RBAC/ABAC, tenant isolation, tool allowlisting, prompt-injection/data-boundary controls, SSRF protections, filesystem confinement, SQL validation, secret abstraction, encryption abstraction, security headers, rate limiting and audit logging.

No claim of 100% security is made.

## 25. Testing

Final backend regression command:

```bash
PYTHONDONTWRITEBYTECODE=1 pytest -q -p no:cacheprovider
```

Final observed result:

```text
273 passed
0 failed
0 skipped
0 warnings
```

Frontend static validation:

```bash
node frontend/validate-frontend.mjs
```

Observed result: 19/19 checks passed.

Full frontend runtime test/build could not be executed because dependencies were not installed and registry access was unavailable.

## 26. Deployment

The repository provides backend/frontend Dockerfiles, development Compose and production Compose examples. PostgreSQL and Redis are deliberately expected to be managed services in production.

Production sequence:
1. Build a clean CI workspace from the frozen repository.
2. Install exact Python dependencies from `requirements.txt`.
3. Install frontend dependencies from the committed lockfile once available.
4. Run backend tests/security tests and frontend lint/typecheck/test/build.
5. Build backend/frontend container images.
6. Scan images/dependencies and publish approved images.
7. Provision/configure WAF/LB/Nginx, Entra, PostgreSQL, Redis, storage, monitoring and secret management.
8. Inject environment-specific configuration and secrets through the approved secret mechanism.
9. Run database migration job if/when versioned migrations exist.
10. Start backend/frontend containers.
11. Verify liveness/readiness and authenticated smoke tests.
12. Run staging production-like security and failure simulations.
13. Obtain required human approvals.
14. Promote the approved image digest to production.

## 27. Backup / restore

A non-production restore exercise exists at `scripts/dr_nonprod_restore.py` and uses synthetic state. It verifies checksums and excludes secret-bearing configuration.

Production backups for PostgreSQL, Redis, object/file storage, audit/SIEM and any production vector store remain deployment responsibilities. RPO/RTO values in existing documentation are engineering targets, not approved SLAs.

## 28. Troubleshooting

- **Backend 503 for chat:** default `get_chat_service()` is intentionally unconfigured; deploy the application composition with a concrete ChatService and capability agents.
- **Production startup says Redis package missing:** install exact `requirements.txt` dependencies in the deployment image.
- **Frontend commands fail with missing packages:** run `npm install` in a network-enabled clean environment; for reproducibility, commit the generated lockfile and use `npm ci` thereafter.
- **Database unavailable:** verify `DATABASE_URL`, network policy, TLS/credentials and PostgreSQL availability; do not bypass read-only/authorization controls.
- **OIDC failures:** verify issuer, JWKS, audience, redirect URI and approved algorithm configuration.
- **File access denied:** verify explicit company root configuration and user tenant/department policy.
- **Report download denied:** verify report ownership/permission and non-expired authorization token.
- **Readiness says ready during dependency outage:** current readiness is unconditional; infrastructure should not treat it as a complete dependency-health gate until implemented/approved.

## 29. Known limitations

1. Default ChatService composition is incomplete.
2. Default Knowledge/Email/Data Analysis/Report agents are placeholders.
3. Full Entra browser OIDC/PKCE/session lifecycle is incomplete.
4. Email sending is not implemented.
5. File-upload API is not implemented.
6. Streaming chat is not implemented.
7. Durable production audit/source/conversation/vector storage is not provided.
8. Production report storage is not HA/durable.
9. Complete Redis worker lifecycle is not certified.
10. Readiness is unconditional.
11. Frontend lockfile is absent.
12. Clean frontend build was blocked by environment/network.
13. Docker runtime build was blocked because no container runtime was available.
14. Live PostgreSQL/Redis/Entra/M365/LLM/SIEM infrastructure was not available for final local certification.
15. Report download tokens are URL-based.
16. Tool timeout cannot forcibly terminate arbitrary running Python threads.
17. Voice/avatar capabilities are not implemented.

## 30. Future roadmap

Future work must be approved separately from this frozen release candidate. Examples already identified in the implementation documentation include:
- complete enterprise OIDC/PKCE/session lifecycle;
- production application composition and concrete capability-agent wiring;
- durable enterprise stores;
- complete Redis worker lifecycle;
- deployment-specific readiness checks;
- staging/live provider validation;
- production backup/restore drills;
- browser E2E and load testing;
- future product capabilities such as voice/avatar only if separately approved.

No future feature is included in this frozen package.

# DEVELOPER STARTUP

## Backend — Linux/macOS

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
# Edit .env with LOCAL-ONLY values; never commit it.
uvicorn backend.main:app --reload
```

## Backend — Windows PowerShell

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
# Edit .env with LOCAL-ONLY values; never commit it.
uvicorn backend.main:app --reload
```

Health endpoint: `http://127.0.0.1:8000/api/health`

## Frontend

```bash
cd frontend
npm install
npm run dev
```

For the frozen repository, `npm install` is the currently documented command because no `package-lock.json` is present. Do not use demo mode for production authentication.

# TEST COMMANDS

## Complete backend suite

```bash
PYTHONDONTWRITEBYTECODE=1 pytest -q -p no:cacheprovider
```

## Frontend static validation

```bash
node frontend/validate-frontend.mjs
```

## Frontend runtime suite once dependencies are installed

```bash
cd frontend
npm run lint
npm run typecheck
npm test
npm run build
```

## Compile check

```bash
python -m compileall -q backend tests
```

# DEPLOYMENT

1. Obtain the frozen repository package and verify its SHA-256 checksum.
2. Build from a clean CI runner with network access to approved package registries.
3. Install `requirements.txt` exactly.
4. Install frontend dependencies and run the complete frontend validation/build.
5. Run the complete backend suite.
6. Run dependency/security scanners.
7. Build backend and frontend Docker images.
8. Run container smoke tests and image scanning.
9. Provision managed PostgreSQL and Redis.
10. Configure Entra/OIDC, Microsoft Graph, secret manager, storage, WAF/LB, Nginx, monitoring and SIEM.
11. Apply approved external/versioned database migrations if any are introduced by deployment configuration.
12. Inject secrets without storing them in the repository.
13. Deploy to staging.
14. Execute production-like multi-user authorization, RAG, SQL, file, email, report, dependency-failure, restart and monitoring simulations.
15. Obtain human approvals.
16. Promote the approved image/artifact.

# SECURITY CHECKLIST BEFORE PRODUCTION

- [ ] No real secrets in repository/image/frontend bundle.
- [ ] Entra issuer/audience/JWKS/redirect configuration approved.
- [ ] Authorization-code + PKCE/browser session lifecycle security-reviewed.
- [ ] RBAC/ABAC policy approved by data owners.
- [ ] Tenant isolation verified.
- [ ] LLM confirmed outside the security boundary.
- [ ] Every protected connector independently authorizes access.
- [ ] Tool Gateway is mandatory for AI tool execution.
- [ ] PostgreSQL least-privilege account/RLS/views reviewed.
- [ ] SQL validation and read-only transaction verified.
- [ ] File roots explicitly configured and filesystem permissions reviewed.
- [ ] Microsoft Graph delegated scopes reviewed.
- [ ] Email content treated as untrusted input.
- [ ] RAG source authorization and lineage verified.
- [ ] Prompt-injection controls tested with current live provider configuration.
- [ ] Secret manager/KMS configured.
- [ ] Logs contain no passwords/tokens/API keys/private keys.
- [ ] Audit events are durable and access-controlled.
- [ ] WAF/LB/TLS/Nginx/network egress controls approved.
- [ ] Distributed rate limiting is backed by production Redis.
- [ ] Dependency and container scans pass approved thresholds.
- [ ] Durable backups and restore drills pass.
- [ ] Report download-token transport/logging risk resolved or formally accepted.
- [ ] Production readiness checks validate required dependencies.
- [ ] Security, IAM, DBA, M365, Network, Platform/SRE, SOC, Privacy/Compliance/Legal and Business/Data-owner approvals obtained as applicable.

# FINAL RELEASE CHECKLIST

| Gate | Result |
|---|---|
| Application feature freeze | PASS |
| Backend regression | PASS — 273/273 |
| Frontend static validation | PASS — 19/19 |
| Backend import/compile | PASS |
| Backend testing-profile startup | PASS |
| Health endpoints | PASS |
| Security suite | PASS in available environment |
| Real clean dependency install | BLOCKED by external registry/DNS |
| Frontend runtime build | BLOCKED by missing dependencies/registry |
| Docker runtime/build | BLOCKED — no container runtime |
| Git status | BLOCKED — supplied directory is not a Git checkout |
| Production runtime composition | FAIL / INCOMPLETE |
| Live enterprise infrastructure | NOT EXECUTED |
| Production certification | NOT READY |

# FINAL ARCHITECTURE SUMMARY

```text
                         +----------------------+
                         |       Entra/OIDC      |
                         +----------+-----------+
                                    |
+----------------+      +-----------v-----------+      +----------------+
| React / TS     | ---> | WAF / LB / Nginx     | ---> | FastAPI        |
| Vite frontend  |      +-----------------------+      +-------+--------+
+----------------+                                        |
                                                    AuthN / RBAC / ABAC
                                                            |
                                                     +------v-------+
                                                     | LangGraph    |
                                                     | Orchestrator |
                                                     +------+-------+
                                                            |
                                                     +------v-------+
                                                     | Tool Gateway |
                                                     +------+-------+
                                                            |
                   +----------------+----------------+-------+---------+
                   |                |                |                 |
             Files/Documents   PostgreSQL       Microsoft Graph    Retrieval
                   |                |                |                 |
                   +----------------+----------------+-----------------+
                                                            |
                                                     Data Analysis
                                                            |
                                                        Reports
                                                            |
                                                     Source lineage
```

**Security principle:** the LLM can route/classify/generate, but it cannot authenticate users, grant permissions, construct an authorization bypass, or directly access protected resources. Backend policy and connector boundaries remain authoritative.

**Release conclusion:** the repository is a validated Release Candidate artifact, but the repository itself does not demonstrate a complete production-ready deployment. The final handover therefore records **NOT READY** until the listed runtime composition, clean-build, infrastructure and human-approval gates are completed.
