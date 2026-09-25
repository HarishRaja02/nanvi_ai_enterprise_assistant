from __future__ import annotations

from backend.security.audit import AuditLogger
from backend.security.authorization import AuthorizationService, Permission, Resource, UserAttributes

from .abstraction import DatabaseRepository
from .exceptions import DatabaseAccessDenied
from .models import QueryRequest, QueryResult, TablePolicy
from .sql_validation import SQLValidationPipeline


class DatabaseService:
    """Secure application service between callers/tools and a read-only repository."""

    def __init__(self, repository: DatabaseRepository, authorization: AuthorizationService,
                 audit_logger: AuditLogger, validation: SQLValidationPipeline, tenant_id: str):
        self._repository = repository
        self._authorization = authorization
        self._audit = audit_logger
        self._validation = validation
        self._tenant_id = tenant_id
        if not validation.column_policy_enforced:
            raise ValueError("DatabaseService requires an explicit column allowlist")

    def execute_read(self, user: UserAttributes, request: QueryRequest) -> QueryResult:
        resource = Resource(
            resource_id="company-postgresql",
            resource_type="company_database",
            tenant_id=self._tenant_id,
        )
        decision = self._authorization.authorize(user, Permission.DATABASE_READ, resource)
        if not decision.allowed:
            self._audit.record(
                "database_access", "deny", user.user_id, user.tenant_id, resource.resource_id,
                {"reason": decision.reason},
            )
            raise DatabaseAccessDenied("Database access denied by authorization policy")

        references = self._validation.validate_read(request.sql, require_bounded_result=True)
        result = self._repository.execute_read(request)
        self._audit.record(
            "database_access", "allow", user.user_id, user.tenant_id, resource.resource_id,
            {"operation": "read", "tables": [f"{s}.{t}" for s, t in references],
             "row_count": len(result.rows), "truncated": result.truncated},
        )
        return result


class DatabaseTool:
    """Secure capability boundary intended for a future AI/tool layer.

    It accepts a user identity and a query request only. It exposes neither credentials
    nor a database connection and therefore cannot bypass DatabaseService controls.
    """

    def __init__(self, service: DatabaseService):
        self._service = service

    def read(self, user: UserAttributes, sql: str, parameters: tuple = ()) -> QueryResult:
        return self._service.execute_read(user, QueryRequest(sql=sql, parameters=parameters))
