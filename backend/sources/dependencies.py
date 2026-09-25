from backend.security.audit import AuditLogger, InMemoryAuditSink
from backend.security.authorization import AuthorizationService
from .service import SourceReferenceService
from .store import InMemorySourceReferenceStore

# Application-scoped dependencies. The in-memory store is suitable for the current
# prototype/test phase; production should replace it with a durable repository.
_source_store = InMemorySourceReferenceStore()
_source_audit = AuditLogger(InMemoryAuditSink())
_source_service = SourceReferenceService(AuthorizationService(), _source_audit, _source_store)


def get_source_reference_service() -> SourceReferenceService:
    return _source_service


def get_source_store() -> InMemorySourceReferenceStore:
    return _source_store
