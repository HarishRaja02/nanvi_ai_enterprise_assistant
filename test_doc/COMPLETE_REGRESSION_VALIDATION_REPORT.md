# Nanvi AI Enterprise Assistant — Complete Regression Validation

Date: 2026-09-18

## Scope

Regression coverage was executed across the existing backend suite, including unit, integration, API, authentication, authorization, RBAC, ABAC, Tool Gateway, RAG/retrieval, SQL/database, files/documents, email, reports, AI security, prompt injection, performance, failure recovery, disaster recovery, observability, and production-hardening tests.

Frontend static validation was also executed. Frontend runtime unit/build tests and Docker runtime builds were environment-blocked because the test environment had no installed frontend dependencies and no Docker/Podman/Buildah/Nerdctl runtime.

## Final automated results

- Backend pytest tests: **264 PASS, 0 FAIL, 0 SKIPPED, 0 WARNINGS**
- Frontend static validation: **19 PASS**
- Frontend Vitest unit tests: **BLOCKED / NOT EXECUTED** — `node_modules` absent and npm registry installation timed out.
- Frontend production build: **BLOCKED / NOT EXECUTED** — same dependency condition.
- Docker runtime tests/builds: **BLOCKED / NOT EXECUTED** — Docker-compatible runtime is not installed in the environment.

### Exact pytest result

`264 passed in 3.20s`

## Requested coverage

| Requested area | Result |
|---|---|
| Backend unit tests | PASS |
| Frontend unit tests | BLOCKED by missing dependencies |
| Integration tests | PASS |
| API tests | PASS |
| Authentication tests | PASS |
| Authorization tests | PASS |
| RBAC tests | PASS |
| ABAC tests | PASS |
| Tool Gateway tests | PASS |
| RAG tests | PASS |
| SQL tests | PASS |
| File tests | PASS |
| Email tests | PASS |
| Report tests | PASS |
| AI-security tests | PASS |
| Prompt-injection tests | PASS |
| Performance tests | PASS |
| Failure-recovery tests | PASS |
| Frontend build tests | BLOCKED by missing dependencies |
| Docker tests | BLOCKED by missing Docker runtime |

## Findings and fixes

### 1. Authentication test warning

The existing expired-token regression test used an 11-byte HMAC key, which caused PyJWT `InsecureKeyLengthWarning` twice.

Fix: changed the test-only fixture key to a sufficiently long value. This does not weaken the test or alter production authentication behavior.

Affected test was rerun: **5 passed, 0 warnings**.

The complete suite was then rerun successfully.

### 2. Frontend Dockerfile pre-flight defect

The frontend Dockerfile used `npm ci` but the repository did not contain `package-lock.json`. `npm ci` therefore could not be a valid clean-build command for the current repository state.

Fix: changed the Docker build step to:

`npm install --no-audit --no-fund`

Added a regression test covering the repository's package-lock/build-command consistency.

The new Docker configuration tests passed: **3 passed**.

A real Docker build could not be executed because no Docker-compatible runtime exists in this environment.

## Frontend validation

The repository's static frontend validator was executed:

**19 static frontend checks passed.**

It verified API typing, authentication/session handling, logout, role UI boundaries, source authorization boundaries, report URL handling, loading/error states, keyboard behavior, query limits, responsive behavior, reduced-motion support, and the presence of test/typecheck/lint/build scripts.

`npm test`, `npm run typecheck`, `npm run lint`, and `npm run build` could not be executed because `node_modules` is unavailable. Two installation attempts using npm timed out; an offline package-lock generation attempt also failed because required packages were not cached.

## Docker validation

Static Docker configuration checks passed, including:

- backend pinned requirements installation
- unprivileged backend runtime user
- frontend build command consistency
- expected PostgreSQL/Redis development services
- PostgreSQL persistent volume definition

A real `docker build` / `docker compose` test was not possible because `docker`, `podman`, `buildah`, and `nerdctl` are not installed.

## Final status

**No executable backend regression test failed.**

No test was weakened or removed to obtain a pass.

The two original PyJWT warnings were eliminated by correcting the test fixture. The remaining unexecuted areas are infrastructure/environment blockers rather than passing test results and must not be represented as validated runtime behavior until executed in an environment with Node dependencies and Docker.
