# System Architecture Diagram

## Implemented architecture

```mermaid
flowchart LR
    U[User / Browser]
    FE[React + TypeScript + Vite]
    API[FastAPI API]
    CTX[Request Context
request/correlation/trace IDs]
    AUTH[Authentication
JWT + OIDC/JWKS validation]
    AUTHZ[Authorization
RBAC + ABAC]
    ORCH[LangGraph Orchestrator
router + capability nodes]
    GW[Secure Tool Gateway
allowlist + auth + policy + budget + timeout + output validation]
    FILE[File Service
LocalFileRepository]
    DOC[Document Parsers]
    RET[Retrieval Service
keyword + vector + authorization]
    DB[Database Service
SQL validator + PostgreSQL repository]
    MAIL[Email Service
Microsoft Graph provider]
    REP[Report Service
XLSX/PDF/DOCX/PPTX]
    SRC[Source Reference Service]
    AUD[Audit Logger]
    OBS[JSON Logs / Optional OTel]
    JOB[Redis Job Queue / Worker contract]

    U --> FE --> API
    API --> CTX
    API --> AUTH --> AUTHZ
    API --> ORCH
    ORCH --> GW
    GW --> AUTHZ
    GW --> FILE
    GW --> DB
    GW --> MAIL
    GW --> RET
    GW --> REP
    FILE --> DOC --> RET
    DB --> SRC
    MAIL --> SRC
    RET --> SRC
    REP --> SRC
    API --> SRC
    AUTH --> AUD
    AUTHZ --> AUD
    GW --> AUD
    FILE --> AUD
    DB --> AUD
    MAIL --> AUD
    RET --> AUD
    REP --> AUD
    API --> OBS
    ORCH --> OBS
    GW --> OBS
    DB --> OBS
    MAIL --> OBS
    FILE --> OBS
    JOB --> OBS
```

## Important implementation boundary

The diagram shows interfaces and existing service boundaries, not a claim that every edge is wired in the default application composition. In particular, concrete Knowledge/Email/Data Analysis/Report capability agents are not currently wired into the default `EnterpriseOrchestrator`.

## Planned/Future

Durable production stores, real LLM provider execution, distributed workers, managed SIEM/OTel and production OIDC callback/session handling remain deployment/integration work.

## Status classification

### Implemented
The diagram reflects implemented modules and their security/observability boundaries.

### Partially implemented
Some diagram edges are architectural relationships rather than default runtime wiring, especially capability-agent-to-tool integrations.

### Planned/Future
Durable infrastructure and complete production provider wiring remain future deployment work.
