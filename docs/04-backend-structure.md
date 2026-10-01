# Backend Structure

## Implemented directories

```text
backend/
├── api/            HTTP routes
├── agents/         LangGraph state, routers, capability contracts, security gateway
├── analysis/       deterministic analysis and lineage models
├── chat/           conversation/chat service and models
├── core/           settings and resilience primitives
├── database/       migration policy marker
├── documents/      document models, parsers and processing service
├── integrations/   files, database and email adapters
├── jobs/           Redis enqueue contract and worker contract
├── observability/  JSON logging, request context and optional OTel
├── reports/        report models, generators, storage and service
├── retrieval/      chunking, embeddings, keyword/vector/reranking/authorization
├── security/       authentication, authorization, audit, AI security, secrets, encryption, headers, rate limiting, validation
├── sources/        opaque source-reference service/store
└── repositories/   reserved repository package; concrete repository code currently lives in integration modules
```

## Key design rules

- API routes do not contain connector credentials.
- Security decisions are outside AI routing.
- Integrations expose application-safe service boundaries.
- Domain models and schemas are kept separate from HTTP concerns where implemented.
- Report generators are formatters, not authorization components.

## Partially implemented

Some package directories are architectural extension points rather than fully populated production subsystems. `repositories/`, `services/`, `models/`, `schemas/` and `tools/` contain limited or marker content compared with the implemented integration/service packages.

## Planned/Future

Further decomposition can move application composition into an explicit dependency container so the default FastAPI app can wire concrete database, email, retrieval, report and chat services without module-level singleton objects.
