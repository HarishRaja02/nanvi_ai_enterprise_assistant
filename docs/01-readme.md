# Nanvi AI Enterprise Assistant — Project Documentation

## Scope and status

This documentation describes the code that is present in this repository as of 2026-09-18. It deliberately distinguishes working implementation from partial wiring and future extension points.

### Implemented
- FastAPI backend with health, authentication identity, chat, source-reference and report-download routes.
- React + TypeScript + Vite frontend.
- OIDC-compatible bearer-token validation using JWT/JWKS, issuer, audience, required claims and an allowed-algorithm list.
- Central RBAC + ABAC authorization independent of AI/LLM logic.
- Reusable security modules for audit, rate limiting, headers, validation, secrets and encryption abstractions.
- Secure local-file access with allowlisted roots, path/symlink/size/type controls.
- PDF, DOCX, XLSX, CSV, TXT/MD and PPTX parsing.
- Provider-neutral retrieval interfaces with in-memory keyword/vector implementations and authorization filtering before reranking.
- Read-only PostgreSQL repository/service with SQL validation, table/column allowlists, read-only transactions, limits and retries.
- Microsoft Graph delegated email provider/service/tool with mailbox authorization, bounded search, pagination validation, rate limiting and read-only scope.
- Report generators for XLSX, PDF, DOCX and PPTX with lineage authorization and secure local storage/download tokens.
- LangGraph orchestration shell with deterministic and LLM-assisted routing interfaces.
- Security gateway with allowlist, authorization, input policy, tool-call budget, timeout, output validation and audit.
- Structured observability with request/correlation/trace IDs, JSON logs and secret scrubbing.
- Redis queue enqueue contract and failure-safe worker contract.
- Non-production DR backup/restore exercise for synthetic data.
- Extensive automated backend/security/UAT/performance/failure tests.

### Partially implemented
- Browser production SSO login/callback/session lifecycle is not implemented; frontend can redirect to a configured SSO URL and supports a development demo mode.
- The default orchestrator constructs capability-agent shells, but Knowledge, Email, Data Analysis and Report agents are not wired with concrete implementations. DatabaseAgent is implemented when its tool and planner are injected.
- Chat has no report-creation API route and no streaming endpoint.
- PostgreSQL/Redis/email/vector/reports are not all wired into the default FastAPI dependency container.
- Source references, audit and conversation history use in-memory stores in the current application wiring.
- Vector retrieval is in-memory; the vector interface can be replaced but no durable vector backend is implemented.
- OpenTelemetry is configurable, but full distributed trace propagation/instrumentation depends on deployment infrastructure.
- Frontend runtime unit/build execution requires npm dependencies to be installed; this repository does not contain `frontend/node_modules`.

### Planned/Future extension points present in code
- Durable source-reference, audit, conversation and report storage.
- Managed secret provider and approved encryption/key-management provider.
- Distributed production infrastructure and enterprise SIEM/OTel integration.
- Additional provider implementations behind existing interfaces (for example another email provider or vector store).
- Concrete capability-agent implementations and richer orchestration.
- Browser-managed OIDC callback/session flow and write/action workflows.

## Quick start

### Backend

```bash
python -m venv .venv
# Windows: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn backend.main:app --reload
```

Health: `http://127.0.0.1:8000/api/health`

### Frontend

```bash
cd frontend
npm install
npm run dev
```

### Tests

```bash
pytest -q
cd frontend
npm run lint
npm run typecheck
npm test
npm run build
```

The frontend commands require installed npm dependencies.

## Documentation map

| Document | Topic |
|---|---|
| 02 | Architecture |
| 03 | System architecture diagram |
| 04 | Backend structure |
| 05 | Frontend structure |
| 06 | Authentication |
| 07 | Authorization |
| 08 | RBAC |
| 09 | ABAC |
| 10 | Tool Gateway |
| 11 | Database |
| 12 | RAG / retrieval |
| 13 | File connector |
| 14 | Email connector |
| 15 | Report generation |
| 16 | API |
| 17 | Environment configuration |
| 18 | Deployment |
| 19 | Docker |
| 20 | Testing |
| 21 | Security |
| 22 | Monitoring / observability |
| 23 | Backup / restore |
| 24 | Troubleshooting |
| 25 | Developer setup |
| 26 | Production operations |

## Non-goals of this documentation

This repository does not contain a production database schema, a durable vector database, a production OIDC callback/session implementation, a live LLM provider adapter, an email-send capability, a file-upload API, or a production HA storage platform. Those are not described as completed features here.
