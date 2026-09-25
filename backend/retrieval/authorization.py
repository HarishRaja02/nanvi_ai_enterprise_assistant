from __future__ import annotations
from backend.security.authorization import AuthorizationService, Permission, Resource, UserAttributes
from .models import KnowledgeChunk


class RetrievalAuthorizer:
    """Enforces access before a protected chunk is returned to the caller."""
    def __init__(self, authorization: AuthorizationService):
        self._authorization = authorization

    def allowed(self, user: UserAttributes, chunk: KnowledgeChunk) -> bool:
        access = chunk.source.access
        resource = Resource(
            resource_id=chunk.source.source_id,
            resource_type=access.resource_type,
            tenant_id=access.tenant_id,
            owner_id=access.owner_id,
            department=access.department,
            attributes={"restricted_department": access.restricted_department} if access.restricted_department else {},
        )
        permission = {
            "email": Permission.EMAIL_READ,
            "mail": Permission.EMAIL_READ,
            "email_mailbox": Permission.EMAIL_READ,
            "sql": Permission.DATABASE_READ,
            "postgres": Permission.DATABASE_READ,
            "postgresql": Permission.DATABASE_READ,
            "database": Permission.DATABASE_READ,
            "database_source": Permission.DATABASE_READ,
        }.get(access.resource_type.casefold(), Permission.FILE_READ)
        return self._authorization.authorize(user, permission, resource).allowed
