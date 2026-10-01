# Authorization

## Implemented

Authorization is centralized in `AuthorizationService` and `PermissionPolicy`. It is independent of AI/LLM decisions.

Evaluation order:
1. Tenant must match.
2. User must have at least one recognized role.
3. RBAC must grant the requested permission.
4. Department rules are evaluated for Finance/HR permissions.
5. Resource-level ownership/restricted-department rules are evaluated.

Every decision is auditable and structured allow/deny logs are emitted.

## Permission model

`FILE_READ`, `FILE_WRITE`, `EMAIL_READ`, `EMAIL_SEND`, `DATABASE_READ`, `DATABASE_WRITE`, `REPORT_CREATE`, `REPORT_DOWNLOAD`, `FINANCE_READ`, `HR_READ`, `AUDIT_READ`.

## Implemented boundaries

Authorization is independently enforced by file, database, email, retrieval, report and source-reference services where those services are used.

## Partially implemented

The presence of a permission in the frontend only controls UI visibility. It does not grant backend access. Some future capability APIs do not yet exist, so their authorization boundary cannot be exercised through HTTP today.

## Planned/Future

Keep authorization decisions in backend services even when additional AI agents, connectors or write actions are added. Human approval for sensitive future write actions is not implemented in the current repository.
