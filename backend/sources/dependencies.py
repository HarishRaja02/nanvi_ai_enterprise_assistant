from __future__ import annotations

import threading
from backend.core.config import settings
from backend.security.audit import AuditLogger
from backend.security.authorization import AuthorizationService
from .service import SourceReferenceService
from .store import SourceReferenceStore

_lock = threading.Lock()
_source_store: SourceReferenceStore | None = None
_source_audit: AuditLogger | None = None
_source_service: SourceReferenceService | None = None


def get_source_store() -> SourceReferenceStore:
    global _source_store
    if _source_store is None:
        with _lock:
            if _source_store is None:
                dsn = settings.supabase_database_url or settings.database_url
                if settings.is_production and dsn:
                    from backend.sources.postgres_store import PostgresSourceReferenceStore
                    _source_store = PostgresSourceReferenceStore(dsn)
                else:
                    from .store import InMemorySourceReferenceStore
                    _source_store = InMemorySourceReferenceStore()
    return _source_store


def get_source_audit() -> AuditLogger:
    global _source_audit
    if _source_audit is None:
        with _lock:
            if _source_audit is None:
                dsn = settings.supabase_database_url or settings.database_url
                if settings.is_production and dsn:
                    from backend.security.audit.postgres import PostgresAuditSink
                    _source_audit = AuditLogger(PostgresAuditSink(dsn))
                else:
                    from backend.security.audit import InMemoryAuditSink
                    _source_audit = AuditLogger(InMemoryAuditSink())
    return _source_audit


def get_source_reference_service() -> SourceReferenceService:
    global _source_service
    if _source_service is None:
        with _lock:
            if _source_service is None:
                _source_service = SourceReferenceService(
                    AuthorizationService(),
                    get_source_audit(),
                    get_source_store(),
                )
    return _source_service

