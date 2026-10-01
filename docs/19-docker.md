# Docker
## Status classification

### Implemented
The Dockerfiles and Compose configuration described below are present in the repository.

### Partially implemented
Local runtime build/execution depends on Docker being installed and is not a local certification in this environment.

### Planned/Future
Production image promotion, registry policy and runtime orchestration remain deployment-environment responsibilities.


## Backend image

`deploy/docker/Dockerfile.backend`:
- Python 3.12 slim base.
- Installs pinned `requirements.txt`.
- Creates unprivileged `nanvi` user.
- Runs Uvicorn on port 8000.
- Drops runtime Linux capabilities at Compose level.
- Includes `/api/health/live` health check.

## Frontend image

`deploy/docker/Dockerfile.frontend`:
- Node 22 Alpine build stage.
- `npm install --no-audit --no-fund` because the repository has no package lock file.
- `npm run build`.
- Nginx 1.29 Alpine runtime.
- Read-only/static serving configuration and health check on port 8080.

## Compose

Development Compose provides PostgreSQL 17 and Redis 8 with a persistent PostgreSQL volume. Production example provides API/frontend containers and internal/edge networks but expects managed PostgreSQL/Redis.

## Validation

Static Docker configuration tests are part of the Python test suite. Runtime Docker build/execution depends on a host with Docker/BuildKit.

## Partially implemented

The current execution environment may not contain Docker and therefore cannot provide a local runtime build certification. CI is configured to build the backend image and scan it with Trivy and generate an SBOM.

## Planned/Future

The repository currently has no frontend lock file. Direct frontend dependencies are exact-pinned in `frontend/package.json`, but transitive dependency resolution is not lockfile-reproducible yet. A lockfile should be committed before claiming fully deterministic frontend builds.
