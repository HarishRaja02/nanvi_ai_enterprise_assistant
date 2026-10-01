# Nanvi AI Enterprise Assistant — Production-Like Simulation Report

**Date:** 2026-09-18  
**Environment:** isolated non-production synthetic runtime  
**Production data/secrets:** none used  
**Feature set:** frozen; no product functionality added

## Executive status

**RESULT: NOT PRODUCTION-READY / SIMULATION NOT FULLY CERTIFIED**

The secured synthetic end-to-end application flow passed, including multi-user authorization, retrieval, tool-gateway enforcement, SQL/file controls, report authorization/download, dependency-failure handling, observability, audit events, backend restart, worker recovery simulation, and frontend/backend API contract checks.

The complete production-like simulation cannot be declared fully passed because several infrastructure-level checks could not be executed in this environment, and the report-download API exposes its one-time token in the URL query string. During an HTTP test-client run, the HTTPX request logger demonstrated that this token can appear in request logs. This is inconsistent with the release requirement that sensitive credentials/tokens not be present in logs and remains a release security blocker until the download-token transport/logging path is hardened.

No production secrets or sensitive production data were used.

## 1. Synthetic end-to-end flow

Validated flow:

`synthetic login identity → authorization → question → routing → secured tool call → authorized retrieval/data → deterministic AI answer → source references → report generation → authorized download`

### Result

**PASS** for the isolated synthetic runtime.

Evidence:
- `tests/test_end_to_end.py`
- `tests/test_business_uat.py`
- `tests/test_report_validation.py`
- API report download probe executed against FastAPI `TestClient`

The AI answerer used for this validation is deterministic test infrastructure. No real LLM provider or production credential was used.

## 2. Multi-user authorization

Synthetic users included:

- Employee — Projects
- Finance — Finance
- HR — HR
- employee from a different tenant

Validated:

| Scenario | Result |
|---|---|
| Employee → restricted HR data | PASS — denied |
| Finance → unauthorized HR data | PASS — denied |
| Finance → permitted Finance data | PASS — allowed |
| Authorized employee → permitted project data | PASS — allowed |
| Cross-tenant access | PASS — denied |
| Read vs write separation | PASS |
| Resource ownership enforcement | PASS |

Relevant suites: `test_authorization.py`, `test_business_uat.py`, `test_security_attack_suite.py`.

## 3. LLM authorization-bypass resistance

Validated that:

- the LLM/test answerer does not define authorization;
- an invalid role cannot grant additional permissions;
- a tool request using an unauthorized permission is rejected;
- a cross-tenant tool request is rejected before execution;
- unknown tools are rejected;
- tool policy runs before tool execution;
- sensitive tool output is filtered.

**Result: PASS.**

## 4. Tool Gateway enforcement

Validated the gateway sequence through the existing security tests:

`allowlist → authorization → policy → budget → execution → output validation → audit`

Unauthorized tool execution callbacks were verified not to run.

**Result: PASS.**

## 5. File-system isolation

Validated:

- configured company roots;
- traversal attempts;
- absolute paths;
- Windows drive paths;
- UNC paths;
- symlink escape;
- malicious filenames;
- extension and size limits;
- permission filtering.

**Result: PASS.**

## 6. SQL controls

Validated:

- SELECT-only behavior;
- table allowlisting;
- column allowlisting;
- parameter separation;
- multi-statement injection rejection;
- INSERT/UPDATE/DELETE/DROP/ALTER/TRUNCATE/CREATE rejection;
- cross-tenant denial;
- authorization before repository execution;
- successful access audit events.

**Result: PASS.**

## 7. Reports and download

Validated:

- lineage authorization before report generation;
- restricted lineage rejection;
- cross-tenant rejection;
- private report storage;
- generated XLSX/PDF/DOCX/PPTX validation in the existing report suite;
- authorized temporary download URL;
- authorized download;
- one-time token replay rejection.

**Functional result: PASS.**

### Security logging finding — BLOCKER

The download endpoint currently carries the one-time token in a query parameter. The production-like API probe produced an HTTPX request log containing the full token-bearing URL.

This means a client/proxy/access logger configured to log request URLs can retain the temporary credential.

**Release status for this item: FAIL/BLOCKED.**

This is consistent with the earlier senior-engineer finding that the report download token is transported in the URL query string.

## 8. Dependency failures and recovery

Validated with synthetic dependency failures:

- generic idempotent retry;
- PostgreSQL transient connection retry;
- Microsoft Graph timeout recovery;
- invalid external response handling;
- vector-store failure with keyword fallback;
- controlled document failure;
- worker retry policy;
- Redis queue temporary-unavailability handling;
- gateway timeout auditing;
- report-generation failure without partial persistence.

**Result: PASS for synthetic failure injection.**

### Real infrastructure limitation

No PostgreSQL or Redis service was available in this execution environment. Therefore the actual network connection-pool recovery and real Redis worker lifecycle were not certified against live infrastructure.

## 9. Worker restart

A synthetic worker restart scenario was executed by preserving a synthetic job outside the worker object, recreating the worker, and successfully processing the job after restart.

**Result: PASS as a worker-process recovery simulation.**

This does **not** certify the complete Redis dequeue/ack/requeue lifecycle because the current Redis queue implementation only provides enqueue functionality and there was no live Redis service available.

## 10. Database connection recovery

A synthetic PostgreSQL repository connection failure was injected on the first connection attempt. The retry policy performed the second connection and returned the expected result.

**Result: PASS as a connection-recovery simulation.**

A live PostgreSQL recovery test remains pending external non-production infrastructure.

## 11. Backend restart

The FastAPI application was started, its liveness endpoint was reached, the process was terminated, and a new process was started on the same port. Both independent processes returned:

`{"status":"ok"}`

Both startups completed successfully.

**Result: PASS.**

## 12. Monitoring and logs

Validated structured logs containing:

- request ID;
- correlation ID;
- trace ID;
- event name;
- actor/tenant context where appropriate;
- latency;
- tool execution events;
- dependency failure events;
- authorization outcomes.

Validated redaction of passwords, API keys, bearer tokens, access tokens, refresh tokens and filesystem paths in the Nanvi structured logging layer.

**Application observability tests: PASS.**

**Production-like download-token logging path: BLOCKED**, as described in Section 7.

## 13. Audit events

Validated audit coverage for:

- authorization allow/deny;
- retrieval;
- tool execution;
- database access;
- report creation;
- report download;
- dependency/error paths.

Audit events include investigation context and secret redaction.

**Result: PASS.**

## 14. Frontend/backend communication

The frontend API client and backend API contract were validated through the existing API tests and frontend static validation.

Frontend static validation:

`19 static frontend checks passed.`

Backend API checks validated:

- authenticated session;
- chat request/response;
- source reference opening;
- conversation history;
- validation errors;
- report download URL;
- unauthorized handling.

**Result: PASS for the executable API/static contract validation.**

A real browser build/run could not be certified because the clean environment did not contain `node_modules` and npm registry access timed out.

## 15. Exact commands executed

### Full backend regression

```bash
PYTHONDONTWRITEBYTECODE=1 python -m pytest -q -p no:cacheprovider
```

Result:

`273 passed in 3.26s`

### Production-like security/integration subset

```bash
python -m pytest -q \
  tests/test_end_to_end.py \
  tests/test_business_uat.py \
  tests/test_authorization.py \
  tests/test_security_attack_suite.py \
  tests/test_ai_security.py \
  tests/test_file_document_security.py \
  tests/test_database_integration.py \
  tests/test_report_validation.py \
  tests/test_failure_injection.py \
  tests/test_observability_final.py \
  tests/test_agents.py \
  tests/test_health.py
```

Result:

`130 passed in 2.41s`

### Frontend static validation

```bash
node frontend/validate-frontend.mjs
```

Result:

`19 static frontend checks passed.`

### Backend package build

The environment did not contain the `build` module, so the documented `python -m build` command was unavailable. The equivalent local wheel build was executed:

```bash
python -m pip wheel . --no-deps --no-build-isolation -w /tmp/nanvi_build_rc
```

Result: wheel successfully built.

### Backend startup / health

```bash
python -m uvicorn backend.main:app --host 127.0.0.1 --port 18000
curl -fsS http://127.0.0.1:18000/api/health/live
curl -fsS http://127.0.0.1:18000/api/health
curl -fsS http://127.0.0.1:18000/api/health/ready
```

Results:

- liveness: `{"status":"ok"}`
- health: `{"status":"ok"}`
- readiness: `{"status":"ready"}`

### Backend restart

```bash
python -m uvicorn backend.main:app --host 127.0.0.1 --port 18002
curl -fsS http://127.0.0.1:18002/api/health/live
# terminate process
python -m uvicorn backend.main:app --host 127.0.0.1 --port 18002
curl -fsS http://127.0.0.1:18002/api/health/live
```

Result: both process instances returned HTTP 200 liveness responses.

### Worker/database recovery simulation

A synthetic isolated Python harness injected a transient worker failure and a transient PostgreSQL connection failure and verified recovery.

Result:

- `WORKER_RESTART=PASS`
- `DATABASE_CONNECTION_RECOVERY=PASS`

### Frontend clean install attempt

```bash
cd frontend
npm install --package-lock-only --ignore-scripts --no-audit --no-fund
```

Result: timed out because external npm registry access was unavailable.

### Docker availability

```bash
docker --version
podman --version
```

Result: neither runtime is installed in this environment. Docker image build could not be executed.

## 16. Infrastructure certification gaps

The following are not claimed as passed:

1. Real PostgreSQL connection recovery against a non-production PostgreSQL service.
2. Real Redis queue/worker restart and dequeue/ack/requeue behavior.
3. Real container image build/run/health checks because no container runtime is installed.
4. Clean frontend dependency installation and Vite build because npm registry access timed out.
5. Live enterprise identity-provider login/PKCE lifecycle.
6. Live external LLM provider execution.
7. Durable production audit/vector/report storage recovery.

These are environment/integration limitations, not silently converted into PASS results.

## 17. Final release decision

**Do not declare Nanvi production-ready.**

The synthetic security and application simulation passed its executable checks, but the full requested production-like simulation is **not fully certified**.

Primary release blockers:

- report download token exposure through URL/query-string logging;
- absence of live PostgreSQL/Redis infrastructure for recovery certification;
- absence of Docker runtime for image build/runtime certification;
- inability to install frontend dependencies and execute the clean frontend build in this environment.

No production secrets or sensitive production data were used, and no new product functionality was introduced during this simulation.
