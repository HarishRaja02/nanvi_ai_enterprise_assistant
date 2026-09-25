from __future__ import annotations

from typing import Iterable

from backend.integrations.files.exceptions import FileAccessDenied, InvalidFilePath
from backend.integrations.files.models import FileMetadata, FileRecord
from backend.integrations.files.repository import FileRepository
from backend.security.audit import AuditLogger
from backend.security.authorization import AuthorizationService, Permission, Resource, UserAttributes
from backend.observability.logging import log_event
import logging
import time

logger = logging.getLogger(__name__)


class FileService:
    """Application-layer file access enforcing authorization and auditing."""

    def __init__(
        self,
        repository: FileRepository,
        authorization: AuthorizationService,
        audit_logger: AuditLogger,
    ) -> None:
        self._repository = repository
        self._authorization = authorization
        self._audit = audit_logger

    def list_files(self, user: UserAttributes, relative_directory: str = "") -> list[FileMetadata]:
        records = list(self._repository.list_files(relative_directory))
        authorized: list[FileMetadata] = []
        for record in records:
            if self._allowed(user, record, "list"):
                authorized.append(record.metadata)
        return authorized

    def search_by_filename(self, user: UserAttributes, query: str, relative_directory: str = "") -> list[FileMetadata]:
        records = list(self._repository.search_by_filename(relative_directory, query))
        authorized: list[FileMetadata] = []
        for record in records:
            if self._allowed(user, record, "search"):
                authorized.append(record.metadata)
        return authorized

    def get_metadata(self, user: UserAttributes, relative_path: str) -> FileMetadata:
        record = self._repository.get_metadata(relative_path)
        self._require_read(user, record, "metadata")
        return record.metadata

    def read_for_processing(self, user: UserAttributes, relative_path: str) -> tuple[FileMetadata, bytes]:
        """Return authorized file bytes plus safe metadata for document processing."""
        record = self._repository.get_metadata(relative_path)
        self._require_read(user, record, "process")
        started = time.perf_counter()
        try:
            data = self._repository.read_file(record.metadata.relative_path)
        except Exception as exc:
            log_event(logger, "file_connector_failed", logging.ERROR, actor_id=user.user_id, tenant_id=user.tenant_id, operation="process", exception_type=type(exc).__name__, duration_ms=round((time.perf_counter() - started) * 1000, 2))
            raise
        log_event(logger, "file_connector_completed", actor_id=user.user_id, tenant_id=user.tenant_id, operation="process", size_bytes=len(data), duration_ms=round((time.perf_counter() - started) * 1000, 2))
        return record.metadata, data

    def read_file(self, user: UserAttributes, relative_path: str) -> bytes:
        record = self._repository.get_metadata(relative_path)
        self._require_read(user, record, "read")
        # The repository revalidates the normalized/resolved target before opening.
        # Authorization is completed before the actual file-content read.
        started = time.perf_counter()
        try:
            data = self._repository.read_file(record.metadata.relative_path)
        except Exception as exc:
            log_event(logger, "file_connector_failed", logging.ERROR, actor_id=user.user_id, tenant_id=user.tenant_id, operation="read", exception_type=type(exc).__name__, duration_ms=round((time.perf_counter() - started) * 1000, 2))
            raise
        log_event(logger, "file_connector_completed", actor_id=user.user_id, tenant_id=user.tenant_id, operation="read", size_bytes=len(data), duration_ms=round((time.perf_counter() - started) * 1000, 2))
        return data

    def _require_read(self, user: UserAttributes, record: FileRecord, operation: str) -> None:
        if not self._allowed(user, record, operation):
            raise FileAccessDenied("File access denied by authorization policy")

    def _allowed(self, user: UserAttributes, record: FileRecord, operation: str) -> bool:
        resource = self._resource_for(record, user.tenant_id)
        decision = self._authorization.authorize(user, Permission.FILE_READ, resource)
        outcome = "allow" if decision.allowed else "deny"
        self._audit.record(
            event_type="file_access",
            outcome=outcome,
            actor_id=user.user_id,
            tenant_id=user.tenant_id,
            resource_id=record.metadata.relative_path,
            metadata={"operation": operation, "reason": decision.reason},
        )
        return decision.allowed

    @staticmethod
    def _resource_for(record: FileRecord, tenant_id: str) -> Resource:
        parts = record.metadata.relative_path.split("/")
        top_level = parts[0].casefold() if parts else ""
        restricted_department = {"hr": "HR", "finance": "Finance"}.get(top_level)
        return Resource(
            resource_id=record.metadata.relative_path,
            resource_type="company_file",
            tenant_id=tenant_id,
            department=restricted_department,
            attributes={"restricted_department": restricted_department},
        )
