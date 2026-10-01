# Nanvi AI Enterprise Assistant — Release Candidate Validation

**Date:** 2026-09-18  
**Status:** RC candidate prepared; environment-blocked release certification

## Feature freeze

No new product functionality was introduced in this RC preparation. Changes were limited to reproducibility, release hygiene, configuration safety, packaging metadata, and documentation.

## Changes made

1. Mirrored the exact runtime dependency pins from `requirements.txt` into `pyproject.toml`.
2. Added direct packages used by the project/test suite to the declared dependency metadata: Pydantic, Starlette, Redis, OpenTelemetry components, cryptography and PyYAML.
3. Fixed setuptools package discovery so `pip wheel .` does not accidentally treat `frontend`, `deploy`, `config` or generated backup directories as Python packages.
4. Removed hard-coded local database passwords from environment examples and Docker Compose; local passwords are now supplied by the developer/environment.
5. Removed the nonexistent frontend lockfile from the CI cache dependency configuration. Frontend direct dependencies remain exact-pinned, but a committed lockfile is still required for deterministic transitive resolution.
6. Updated setup/deployment documentation to reflect the actual reproducibility boundary.

## Exact commands used

### Repository inspection

```bash
find . -maxdepth 2 -type f | sort
python --version
node --version
npm --version
docker --version
```

Observed runtime tools:
- Python 3.13.5
- Node 22.16.0
- npm 10.9.2
- Docker unavailable in the execution environment

### Backend regression

```bash
python -m pytest -q
```

Result after the RC changes:

```text
273 passed in 3.33s
```

### Frontend static validation

```bash
cd frontend
node validate-frontend.mjs
```

Result:

```text
19 static frontend checks passed.
```

### Backend startup and health

```bash
APP_ENV=testing DEBUG=false LOG_LEVEL=WARNING \
COMPANY_FILE_ROOTS='Customers=/tmp/nanvi/Customers;Finance=/tmp/nanvi/Finance;HR=/tmp/nanvi/HR;Projects=/tmp/nanvi/Projects;Contracts=/tmp/nanvi/Contracts' \
DATABASE_URL='postgresql://placeholder' \
REDIS_URL='redis://localhost:6379/1' \
CORS_ORIGINS='http://localhost:5173' \
python -m uvicorn backend.main:app --host 127.0.0.1 --port 18000
```

Then:

```bash
curl -fsS http://127.0.0.1:18000/api/health/live
curl -fsS http://127.0.0.1:18000/api/health/ready
```

Observed:

```text
{"status":"ok"}
{"status":"ready"}
```

The response included request, correlation and trace IDs plus security headers.

### Clean Python environment installation

```bash
rm -rf /tmp/nanvi-rc-venv
python -m venv /tmp/nanvi-rc-venv
/tmp/nanvi-rc-venv/bin/python -m pip install --upgrade pip
/tmp/nanvi-rc-venv/bin/pip install -r requirements.txt
```

This could not complete because the execution environment has no external DNS/package-registry access. This is an infrastructure limitation of the validation environment, not a dependency-resolution error in the repository.

An offline check also confirmed there is no local wheel cache sufficient to install the pinned dependency set into a clean environment.

### Python package build

Initial command:

```bash
python -m pip wheel . --no-deps --no-build-isolation -w /tmp/nanvi-wheel
```

Initial result: failed because setuptools automatically discovered multiple top-level directories.

Fix applied: explicit setuptools package discovery in `pyproject.toml`.

Re-run:

```bash
python -m pip wheel . --no-deps --no-build-isolation -w /tmp/nanvi-wheel-fixed
```

Result: **PASS**; wheel built successfully.

### Frontend dependency installation/build

Attempted:

```bash
cd frontend
npm install --package-lock-only --ignore-scripts --no-audit --no-fund
```

Result: timed out because the environment could not reach the npm registry.

`frontend/node_modules` is absent, therefore these were not counted as passed:

```bash
npm run lint
npm run typecheck
npm test
npm run build
```

### Docker

```bash
docker --version
```

Result: Docker is not installed in the validation environment. Therefore runtime Docker image builds and container health checks could not be executed locally.

Static Docker configuration remains covered by the backend test suite.

### Dependency check

```bash
python -m pip check
```

The current shared environment reports an unrelated conflict:

```text
moviepy 2.2.1 requires pillow<12.0,>=9.2.0, but pillow 12.3.0 is installed.
```

`moviepy` is not a Nanvi dependency. It was not added to or altered in the Nanvi dependency set.

## Release hygiene verification

### Secrets

No production credential values were found in source/configuration. Local database passwords were removed from example configuration.

Test files intentionally contain synthetic tokens/password strings to verify secret redaction. These are not deployment credentials and are only used as security-test fixtures.

### Debug code

No `breakpoint()`, `pdb.set_trace()`, or browser `debugger` statements were found in application code.

Development configuration may enable `DEBUG=true` in its example environment; production configuration explicitly sets `DEBUG=false`. This is configuration behavior, not debug code.

### Temporary/generated files

Generated caches, Python bytecode, build output, package metadata, validation ZIPs and generated result/log artifacts were removed from the RC tree.

### Production URLs

Intentional fixed external endpoints remain only where required by the implemented integration/configuration, notably Microsoft Graph's API base. Deployment-specific URLs such as OIDC issuer, redirect URI, CORS origin and OTEL endpoint remain configuration values/placeholders.

### Migrations

The repository contains a migration policy marker only. There is currently no application database schema or automatic startup DDL. No migration was invented during RC preparation.

## Final certification matrix

| Check | Status | Notes |
|---|---|---|
| Clean repository | PASS | Generated/cache/build artifacts removed |
| No production secrets | PASS | Static scan + configuration review |
| No debug code | PASS | Static scan |
| No temporary files | PASS | RC tree cleaned |
| No deployment test credentials | PASS | Local passwords replaced with placeholders/env input |
| Production URLs intentionally configured | PASS | Fixed Graph endpoint is intentional |
| Dependency versions | PASS | Exact pins mirrored; frontend direct pins exact |
| Migrations | PASS | No required schema/migrations exist |
| Docker build | BLOCKED | Docker unavailable |
| Frontend build | BLOCKED | npm registry unavailable; no node_modules |
| Backend startup | PASS | Uvicorn startup verified |
| Health checks | PASS | liveness/readiness endpoints responded |
| Backend test suite | PASS | 273 passed |
| Security suite | PASS | Included in 273-test suite |
| Configuration | PASS | Production defaults and placeholders reviewed |
| Documentation | PASS | Setup/deployment/reproducibility docs updated |
| Python package build | PASS | Wheel built after package-discovery fix |

## RC conclusion

Nanvi is prepared as a **release-candidate code freeze**, but this environment does not permit full release certification because it cannot reach package registries and does not provide Docker.

The remaining certification commands that must run on a network-enabled clean CI/staging runner are:

```bash
cd frontend
npm install
npm run lint
npm run typecheck
npm test
npm run build

cd ..
python -m venv .venv
# activate .venv
python -m pip install -r requirements.txt
python -m pytest -q

docker build -f deploy/docker/Dockerfile.backend -t nanvi-api:rc .
docker build -f deploy/docker/Dockerfile.frontend -t nanvi-frontend:rc .
```

A frontend `package-lock.json` should be generated and committed on that network-enabled runner before declaring fully deterministic frontend dependency resolution.
