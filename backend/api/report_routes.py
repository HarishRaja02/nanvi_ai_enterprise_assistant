from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
import re

from backend.security.authorization import UserAttributes
from backend.security.authorization.rbac import Role
from backend.security.dependencies import get_current_user
from backend.security.models import UserIdentity
from backend.reports.service import ReportAuthorizationError, ReportService
from backend.reports.storage import ReportNotFound, SecureFileReportStorage
from backend.security.audit import AuditLogger, InMemoryAuditSink
from backend.security.authorization import AuthorizationService

router = APIRouter(prefix="/reports", tags=["reports"])

def _safe_download_filename(title: str, extension: str) -> str:
    cleaned = re.sub(r'[\x00-\x1f\x7f\\/:*?\"<>|]+', '_', title).strip(' .')
    cleaned = cleaned[:120] or "nanvi-report"
    return f"{cleaned}.{extension}"

# Dependency wiring is intentionally explicit. Production should provide a shared
# ReportStorage and AuditSink through the application's dependency container.
_storage = SecureFileReportStorage("backend/storage/reports")
_audit = AuditLogger(InMemoryAuditSink())
_service = ReportService(_storage, AuthorizationService(), _audit)


def get_report_service() -> ReportService:
    return _service


from fastapi.security import HTTPAuthorizationCredentials
from backend.security.dependencies import _bearer, get_authentication_service
from backend.security.authentication_service import AuthenticationService

def get_optional_user_attributes(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    auth_service: AuthenticationService = Depends(get_authentication_service),
) -> UserAttributes | None:
    if credentials is None or credentials.scheme.lower() != "bearer":
        return None
    try:
        user = auth_service.authenticate_access_token(credentials.credentials)
        if not user.tenant_id or not user.roles:
            return None
        return UserAttributes(
            user_id=user.subject,
            tenant_id=user.tenant_id,
            department=user.department,
            roles=user.roles,
        )
    except Exception:
        return None


def get_current_user_attributes(identity: UserIdentity = Depends(get_current_user)) -> UserAttributes:
    if not identity.tenant_id or not identity.roles:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Authorization context is incomplete")
    return UserAttributes(
        user_id=identity.subject,
        tenant_id=identity.tenant_id,
        department=identity.department,
        roles=identity.roles,
    )


@router.post("/{report_id}/download-url")
def create_download_url(
    report_id: str,
    ttl_seconds: int = Query(default=300, ge=1, le=3600),
    user: UserAttributes = Depends(get_current_user_attributes),
    service: ReportService = Depends(get_report_service),
):
    try:
        return {"download_url": service.issue_temporary_download_url(user, report_id, ttl_seconds)}
    except ReportAuthorizationError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")


@router.get("/{report_id}/download")
@router.get("/download/{report_id}")
def download_report(
    report_id: str,
    token: str = Query(..., min_length=20, max_length=512),
    user: UserAttributes | None = Depends(get_optional_user_attributes),
    service: ReportService = Depends(get_report_service),
):
    try:
        if user is None:
            metadata = service._storage.get(report_id)
            user = UserAttributes(
                user_id=metadata.owner_id,
                tenant_id=metadata.tenant_id,
                department=None,
                roles=frozenset({Role.CEO, Role.FINANCE, Role.EMPLOYEE}),
            )
        path, metadata = service.open_download(user, report_id, token)
    except (ReportAuthorizationError, ReportNotFound):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found or download token invalid")
    media_type_map = {
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "pdf": "application/pdf",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "txt": "text/plain; charset=utf-8",
    }
    return FileResponse(
        path,
        filename=_safe_download_filename(metadata.title, metadata.format.value),
        media_type=media_type_map.get(metadata.format.value, "application/octet-stream"),
    )
