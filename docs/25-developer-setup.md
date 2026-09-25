# Developer Setup

## Prerequisites

- Python 3.11+ (CI uses 3.12).
- Node 22 for frontend work.
- PostgreSQL/Redis only when testing those real integrations.
- Docker only when building/running containers.

## Backend

```bash
python -m venv .venv
# Windows PowerShell
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Copy `.env.example` to your local environment, replace placeholders with local-only values, and never commit secrets.

Start:

```bash
uvicorn backend.main:app --reload
```

## Frontend

```bash
cd frontend
npm install
npm run dev
```

For development-only demo identity, set `VITE_DEMO_MODE=true`. Do not use demo mode as production authentication.

## Tests

```bash
cd ..
pytest -q
cd frontend
npm run lint
npm run typecheck
npm test
npm run build
```

## Architecture rules for contributors

- Keep auth/authz independent from AI code.
- Never place secrets in prompts, graph state, logs or frontend variables.
- Put protected operations behind service boundaries and authorization.
- Keep file/database/email credentials inside integration infrastructure.
- Add a regression test for every defect fixed.
- Do not weaken a security test to make a suite green.
- Document implementation status honestly.

## Partially implemented

There is no local script that automatically composes all enterprise dependencies into a production-like environment. Use the development Compose file for PostgreSQL/Redis infrastructure when needed and inject service dependencies in tests/application composition.

## Planned/Future

A single production-like developer environment is not currently provided; future work can add a reproducible staging/dev stack once the target infrastructure is fixed.

## Status classification

### Implemented
The setup commands, configuration examples and contributor rules above match the current repository.

### Partially implemented
Real enterprise dependencies and production-like integration are not bundled into a single developer command.

### Planned/Future
A reproducible staging-like developer stack can be added after the target infrastructure is fixed.
