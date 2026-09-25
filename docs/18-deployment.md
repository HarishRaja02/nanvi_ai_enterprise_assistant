# Deployment

## Implemented deployment assets

- Backend and frontend Dockerfiles.
- Development Compose file with PostgreSQL and Redis.
- Production Compose example with API/frontend only; PostgreSQL and Redis are intentionally expected to be managed services.
- Nginx frontend configuration.
- Nginx production reverse-proxy example with TLS placeholders and API proxying.
- GitHub Actions CI workflow for backend tests/dependency audit, frontend build/audit, Gitleaks, Docker build/Trivy/SBOM.

## Recommended runtime shape represented by repository

```text
TLS / managed load balancer or Nginx
          |
     React frontend
          |
      FastAPI API
       /       \
  PostgreSQL   Redis
       |
  external IdP / Graph / LLM providers as configured
```

The production Compose example deliberately does not co-locate PostgreSQL or Redis.

## Partially implemented

The repository does not deploy itself to a cloud provider. Managed database, Redis, identity provider, object storage, SIEM/OTel collector, certificates, WAF and backup service must be supplied by the target environment.

## Planned/Future

Staging and production infrastructure should be provisioned separately, with real dependency health checks, secret injection, backups, restore drills and external security controls.
