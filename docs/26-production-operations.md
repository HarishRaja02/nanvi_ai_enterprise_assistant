# Production Operations Guide

## Before deployment

### Identity
- Configure trusted OIDC issuer/JWKS/audience and allowed algorithms.
- Complete and security-review the browser OIDC callback/session implementation before relying on browser SSO.

### Data access
- Provision PostgreSQL with a dedicated least-privilege role.
- Configure explicit file roots.
- Configure Microsoft Graph delegated permissions only as required.
- Ensure every source has tenant/owner/department metadata required by policy.

### Secrets
- Use an approved secret manager.
- Do not place production secrets in `.env.example`, frontend variables, prompts or logs.

### Storage
- Replace in-memory audit/source/conversation/vector stores with durable services.
- Replace local report storage with private durable shared storage if running multiple instances.

### Observability
- Send JSON logs/audit events to the enterprise monitoring/SIEM platform.
- Configure retention and alerts.
- Configure OTLP endpoint if distributed tracing is used.

### Backup/DR
- Configure provider-native backups.
- Test restore in staging/non-production.
- Record RPO/RTO evidence.

## Runtime checks

Monitor:
- authentication failures;
- authorization denials;
- tool timeouts/budget denials;
- database connection failures/latency;
- Microsoft Graph 429/5xx/timeouts;
- retrieval fallback events;
- report generation failures;
- worker failures/retries;
- HTTP 4xx/5xx latency;
- resource saturation at the platform layer.

Use request/correlation/trace IDs to connect an API event to downstream events.

## Incident handling

1. Capture request/correlation/trace ID.
2. Review authentication and authorization events.
3. Review tool/connector events for the same chain.
4. Check whether the event was a dependency outage, policy denial or application error.
5. Preserve audit evidence without copying secrets or business payloads into incident tickets.
6. If data integrity is in question, stop affected writes and follow the approved restore/continuity procedure.

## Current operational limitations

The repository does not provide a production admin console, automatic dependency readiness checks, durable audit service, managed storage integration, complete OIDC session flow or full distributed worker runtime. These must be provided by the deployment environment before claiming enterprise production operations are complete.

## Planned/Future

Add deployment-specific runbooks, alert thresholds, escalation ownership, capacity limits, failover drills and change-management procedures after the target production platform is selected.

## Partially implemented

The repository supplies production-oriented code paths and deployment examples, but the actual production control plane, managed services and complete operational runbooks are external to the repository.

## Planned/Future

Deployment-specific escalation, alert thresholds, capacity planning and failover procedures should be finalized with the production platform and operations owners.

## Status classification

### Implemented
Production-oriented operational controls and guidance in this document correspond to current code and deployment assets.

### Partially implemented
The repository does not itself provide the production control plane, managed services or complete enterprise runbooks.

### Planned/Future
Deployment-specific escalation, alert thresholds, capacity planning and failover procedures require the target production platform.
