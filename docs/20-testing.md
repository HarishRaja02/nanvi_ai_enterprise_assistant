# Testing

## Implemented test suites

The `tests/` directory covers:
- agents/orchestration
- AI security and prompt injection
- answer correctness
- authentication
- authorization/RBAC/ABAC
- business UAT
- database integration and SQL validation
- disaster recovery
- Docker configuration
- document processing and file security/integration
- email integration/security
- end-to-end behavior
- failure injection/resilience
- health
- observability
- performance
- production hardening
- report generation/validation
- retrieval/evaluation
- security attack suite
- source transparency

The current full backend run executed during documentation generation:

```text
273 passed in 3.51s
```

No skipped tests or pytest warnings were reported in that run.

Frontend static validation:

```text
19 static frontend checks passed.
```

## Frontend runtime test status

The repository has Vitest, lint, typecheck and build scripts. In the current working environment `frontend/node_modules` is absent. Running the scripts therefore cannot be treated as a successful runtime build/test execution until dependencies are installed.

## CI

GitHub Actions installs backend dependencies and runs `pytest`, `pip-audit`, frontend `npm install` + build + audit, Gitleaks and backend Docker/Trivy/SBOM steps.

## Partially implemented

Real infrastructure integration tests are environment-dependent. The local suite uses fakes for unavailable PostgreSQL/Redis/Graph/LLM infrastructure in several tests.

## Planned/Future

Run staging integration, chaos/failover, browser E2E and real provider tests before production release.
