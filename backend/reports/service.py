from __future__ import annotations

import tempfile
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from backend.security.audit import AuditLogger
from backend.security.authorization import AuthorizationService, Permission, Resource, UserAttributes
from backend.agents.security_gateway import SecureToolGateway, ToolContext
from backend.observability.logging import log_event
import logging
import time

logger = logging.getLogger(__name__)

from .generators import (
    ExcelReportGenerator,
    PDFReportGenerator,
    WordReportGenerator,
    PowerPointReportGenerator,
    TextReportGenerator,
)
from .models import ReportArtifact, ReportFormat, ReportMetadata, ReportRequest
from .storage import ReportNotFound, ReportStorage, SecureFileReportStorage


class ReportAuthorizationError(PermissionError):
    pass


class ReportService:
    def __init__(self, storage: ReportStorage, authorization: AuthorizationService, audit: AuditLogger,
                 base_download_url: str = "/api/reports/download") -> None:
        self._storage = storage
        self._authorization = authorization
        self._audit = audit
        self._base_download_url = base_download_url.rstrip("/")
        self._generators = {
            ReportFormat.EXCEL: ExcelReportGenerator(),
            ReportFormat.PDF: PDFReportGenerator(),
            ReportFormat.WORD: WordReportGenerator(),
            ReportFormat.POWERPOINT: PowerPointReportGenerator(),
            ReportFormat.TEXT: TextReportGenerator(),
        }

    def create_report(self, user: UserAttributes, request: ReportRequest) -> ReportArtifact:
        if not isinstance(request.format, ReportFormat):
            raise ValueError("Unsupported report format")
        resource = Resource(
            resource_id=request.report_id,
            resource_type="user_report",
            tenant_id=request.tenant_id,
            owner_id=user.user_id,
        )
        decision = self._authorization.authorize(user, Permission.REPORT_CREATE, resource)
        if not decision.allowed:
            self._audit.record("report_creation", "deny", user.user_id, user.tenant_id, request.report_id,
                               {"format": request.format.value, "reason": decision.reason})
            raise ReportAuthorizationError("Report creation denied")
        if request.generated_by != user.user_id or request.tenant_id != user.tenant_id:
            raise ReportAuthorizationError("Report principal mismatch")
        self._authorize_lineage(user, request.lineage)
        try:
            UUID(request.report_id)
        except (ValueError, AttributeError) as exc:
            raise ValueError("report_id must be a UUID") from exc
        generator = self._generators.get(request.format)
        if generator is None:
            raise ValueError("Unsupported report format")
        created_at = datetime.now(timezone.utc)
        metadata = ReportMetadata(
            report_id=request.report_id,
            title=request.title,
            format=request.format,
            owner_id=user.user_id,
            tenant_id=user.tenant_id,
            storage_name="",
            created_at=created_at,
            size_bytes=0,
            lineage=request.lineage,
        )
        started = time.perf_counter()
        with tempfile.TemporaryDirectory(prefix="nanvi-report-") as tmp_dir:
            temp_path = Path(tmp_dir) / f"report.{generator.extension}"
            try:
                generator.generate(request, temp_path)
                metadata = self._storage.save(request.report_id, generator.extension, temp_path, metadata)
            except Exception as exc:
                log_event(logger, "report_generation_failed", logging.ERROR, actor_id=user.user_id, tenant_id=user.tenant_id,
                          report_id=request.report_id, format=request.format.value, exception_type=type(exc).__name__,
                          duration_ms=round((time.perf_counter() - started) * 1000, 2))
                raise
        log_event(logger, "report_generation_completed", actor_id=user.user_id, tenant_id=user.tenant_id,
                  report_id=request.report_id, format=request.format.value, size_bytes=metadata.size_bytes,
                  duration_ms=round((time.perf_counter() - started) * 1000, 2))
        self._audit.record("report_creation", "allow", user.user_id, user.tenant_id, request.report_id,
                           {"format": request.format.value, "size_bytes": metadata.size_bytes,
                            "sources": [x.source_id for x in request.lineage]})
        return ReportArtifact(metadata, f"{self._base_download_url}/{request.report_id}")

    def _authorize_lineage(self, user: UserAttributes, lineage) -> None:
        """Fail closed unless every declared data source is authorized for this user.

        Report generators are intentionally dumb formatters. The service is the
        security boundary that verifies provenance before any bytes are generated.
        Upstream analysis/database/file services must supply tenant and resource
        metadata; missing authorization context is never treated as public data.
        """
        if not lineage:
            raise ReportAuthorizationError("Report requires authorized source lineage")

        permission_map = {
            "file": Permission.FILE_READ,
            "document": Permission.FILE_READ,
            "pdf": Permission.FILE_READ,
            "docx": Permission.FILE_READ,
            "xlsx": Permission.FILE_READ,
            "csv": Permission.FILE_READ,
            "txt": Permission.FILE_READ,
            "pptx": Permission.FILE_READ,
            "sql": Permission.DATABASE_READ,
            "postgres": Permission.DATABASE_READ,
            "postgresql": Permission.DATABASE_READ,
            "database": Permission.DATABASE_READ,
            "internal": Permission.REPORT_CREATE,
            "system": Permission.REPORT_CREATE,
            "conversation": Permission.REPORT_CREATE,
            "email": Permission.EMAIL_READ,
            "mail": Permission.EMAIL_READ,
        }
        for item in lineage:
            if not item.tenant_id or not item.source_id or not item.resource_type:
                raise ReportAuthorizationError("Report source authorization context is incomplete")
            try:
                permission = permission_map[item.source_type.casefold()]
            except KeyError as exc:
                raise ReportAuthorizationError("Report source type is not authorized") from exc
            resource = Resource(
                resource_id=item.source_id,
                resource_type=item.resource_type,
                tenant_id=item.tenant_id,
                owner_id=item.owner_id,
                department=item.department,
                attributes={"restricted_department": item.restricted_department}
                if item.restricted_department else {},
            )
            decision = self._authorization.authorize(user, permission, resource)
            if not decision.allowed:
                self._audit.record("report_data_authorization", "deny", user.user_id, user.tenant_id,
                                   item.source_id, {"source_type": item.source_type, "reason": decision.reason})
                raise ReportAuthorizationError("Report contains unauthorized source data")

    def issue_temporary_download_url(self, user: UserAttributes, report_id: str, ttl_seconds: int = 300) -> str:
        metadata = self._get_authorized_report(user, report_id)
        token, _ = self._storage.issue_download_token(report_id, ttl_seconds)
        self._audit.record("report_download_url", "allow", user.user_id, user.tenant_id, report_id,
                           {"ttl_seconds": ttl_seconds})
        return f"{self._base_download_url}/{report_id}?token={token}"

    def open_download(self, user: UserAttributes, report_id: str, token: str):
        metadata = self._get_authorized_report(user, report_id)
        try:
            consumed = self._storage.consume_download_token(report_id, token)
            path = self._storage.open_path(consumed)
        except ReportNotFound:
            self._audit.record("report_download", "deny", user.user_id, user.tenant_id, report_id,
                               {"reason": "Invalid, expired, or already-used download token"})
            raise
        self._audit.record("report_download", "allow", user.user_id, user.tenant_id, report_id,
                           {"format": metadata.format.value, "size_bytes": metadata.size_bytes})
        return path, metadata

    def _get_authorized_report(self, user: UserAttributes, report_id: str) -> ReportMetadata:
        try:
            metadata = self._storage.get(report_id)
        except ReportNotFound as exc:
            raise ReportAuthorizationError("Report not found") from exc
        resource = Resource(resource_id=report_id, resource_type="user_report", tenant_id=metadata.tenant_id, owner_id=metadata.owner_id)
        decision = self._authorization.authorize(user, Permission.REPORT_DOWNLOAD, resource)
        if not decision.allowed:
            self._audit.record("report_download", "deny", user.user_id, user.tenant_id, report_id,
                               {"reason": decision.reason})
            raise ReportAuthorizationError("Report download denied")
        return metadata
