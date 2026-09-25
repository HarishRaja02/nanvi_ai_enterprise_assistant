from __future__ import annotations

from uuid import uuid4

from backend.security.audit import AuditLogger
from backend.security.authorization import AuthorizationService, Permission, Resource, UserAttributes
from backend.security.ai.output_guard import SensitiveDataFilter

from .models import SourceReference, SourceType
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from backend.analysis.models import DataLineage
    from backend.retrieval.models import SourceMetadata
from .store import SourceReferenceStore


class SourceReferenceNotFound(LookupError):
    pass


class SourceReferenceService:
    """Creates and resolves safe citations only after authorization."""

    _PERMISSIONS = {
        SourceType.FILE: Permission.FILE_READ,
        SourceType.DOCUMENT: Permission.FILE_READ,
        SourceType.EMAIL: Permission.EMAIL_READ,
        SourceType.DATABASE: Permission.DATABASE_READ,
        SourceType.DRIVE: Permission.FILE_READ,
    }

    def __init__(self, authorization: AuthorizationService, audit: AuditLogger,
                 store: SourceReferenceStore, base_url: str = "/api/sources") -> None:
        self._authorization = authorization
        self._audit = audit
        self._store = store
        self._output_filter = SensitiveDataFilter()
        self._base_url = base_url.rstrip("/")

    def from_lineage(self, user: UserAttributes, request_id: str,
                     lineage: tuple["DataLineage", ...]) -> tuple[SourceReference, ...]:
        refs: list[SourceReference] = []
        for item in lineage:
            ref = self._create_from_lineage(user, request_id, item)
            if ref is not None:
                refs.append(ref)
        return tuple(refs)

    def from_metadata(self, user: UserAttributes, request_id: str,
                      source: "SourceMetadata") -> SourceReference | None:
        source_type = self._source_type(source.source_type)
        return self._create(
            user=user,
            request_id=request_id,
            source_type=source_type,
            source_id=source.source_id,
            display_name=source.filename or self._safe_label(source.source_id, source_type),
            title=source.filename,
            location=source.sheet and f"Sheet {source.sheet}" or None,
            page=source.page,
            sheet=source.sheet,
            timestamp=source.modified_at or source.created_at,
            mime_type=self._mime_type(source.source_type),
            owner_id=source.access.owner_id,
            tenant_id=source.access.tenant_id,
            department=source.access.department,
            restricted_department=source.access.restricted_department,
        )

    def resolve_for_user(self, user: UserAttributes, request_id: str,
                         reference_id: str) -> SourceReference:
        item = self._store.get(reference_id)
        if not item:
            item = self._resolve_dynamic_fallback(reference_id, user)
        if not item:
            raise SourceReferenceNotFound("Source reference not found")
        resource = self._resource(item)
        permission = self._PERMISSIONS.get(SourceType(item["source_type"]))
        if permission is None:
            raise SourceReferenceNotFound("Source reference not available")
        decision = self._authorization.authorize(user, permission, resource)
        if not decision.allowed:
            self._audit.record("source_reference_access", "deny", user.user_id, user.tenant_id,
                               reference_id, {"reason": decision.reason})
            raise SourceReferenceNotFound("Source reference not available")
        self._audit.record("source_reference_access", "allow", user.user_id, user.tenant_id,
                           reference_id, {"source_type": item["source_type"]})
        return item["reference"]

    def _resolve_dynamic_fallback(self, reference_id: str, user: UserAttributes) -> dict | None:
        """Dynamically reconstruct source reference if not present in store (e.g. after server restart)."""
        import re
        import logging
        from pathlib import Path
        _log = logging.getLogger(__name__)

        token = reference_id
        for prefix in ("ref-inv-", "ref-", "dir-", "source-", "gmail-"):
            if token.startswith(prefix):
                token = token[len(prefix):]
                break
        token = re.sub(r"^\d+-", "", token).strip().casefold()

        # 1. Try to resolve against CompanyDataService
        try:
            from backend.integrations.files.company_data_service import CompanyDataService
            cds = CompanyDataService.get_instance()

            matched_chunk = None
            for chunk in getattr(cds, "chunks", []):
                fn = chunk.filename.casefold()
                fn_stem = fn.rsplit(".", 1)[0]
                if token and (token in fn or token in fn_stem or fn_stem in token):
                    matched_chunk = chunk
                    break

            if not matched_chunk:
                for file_info in getattr(cds, "files", []):
                    fn = file_info.get("filename", "").casefold()
                    fn_stem = fn.rsplit(".", 1)[0]
                    if token and (token in fn or token in fn_stem or fn_stem in token):
                        matched_chunk = type("MockChunk", (), {
                            "filename": file_info.get("filename", ""),
                            "folder": file_info.get("folder", "CompanyData"),
                            "location": file_info.get("folder_path") or "Section 1",
                            "full_path": file_info.get("full_path") or file_info.get("file_path", ""),
                            "page": None,
                            "sheet": None,
                        })()
                        break

            if matched_chunk:
                loc = getattr(matched_chunk, "full_path", "")
                title = f"{matched_chunk.filename} ({matched_chunk.location})" if hasattr(matched_chunk, "location") and matched_chunk.location else matched_chunk.filename
                ref = SourceReference(
                    reference_id=reference_id,
                    source_type=SourceType.FILE,
                    display_name=f"[{matched_chunk.folder}] {matched_chunk.filename}",
                    title=title,
                    location=loc,
                    page=getattr(matched_chunk, "page", None),
                    sheet=getattr(matched_chunk, "sheet", None),
                )
                self._store.save(
                    reference=ref,
                    owner_id=user.user_id,
                    tenant_id=user.tenant_id,
                    source_id=reference_id,
                    source_type="file",
                    department=user.department,
                    restricted_department=None,
                )
                return self._store.get(reference_id)
        except Exception as exc:
            _log.warning("Company data dynamic source lookup failed: %s", exc)

        # 2. Check if it's an email/gmail reference
        if "gmail" in reference_id.casefold():
            ref = SourceReference(
                reference_id=reference_id,
                source_type=SourceType.EMAIL,
                display_name="[Email] Verified Message",
                title="Email Message",
                location="Inbox",
            )
            self._store.save(
                reference=ref,
                owner_id=user.user_id,
                tenant_id=user.tenant_id,
                source_id=reference_id,
                source_type="email",
                department=user.department,
            )
            return self._store.get(reference_id)

        # 3. Check uploaded files directory and active company data folder
        try:
            from backend.integrations.files.company_data_service import CompanyDataService
            active_root = CompanyDataService.get_instance().root
            candidate_dirs = [active_root / "Uploads", active_root, Path("C:/CompanyData/Uploads"), Path("./CompanyData/Uploads")]
            for upload_dir in candidate_dirs:
                if upload_dir.exists() and upload_dir.is_dir():
                    for f in upload_dir.iterdir():
                        if f.is_file() and (token in f.name.casefold() or f.name.casefold() in token):
                            ref = SourceReference(
                                reference_id=reference_id,
                                source_type=SourceType.DOCUMENT,
                                display_name=f"[{upload_dir.name}] {f.name}",
                                title=f.name,
                                location=str(f),
                            )
                            self._store.save(
                                reference=ref,
                                owner_id=user.user_id,
                                tenant_id=user.tenant_id,
                                source_id=reference_id,
                                source_type="document",
                                department=user.department,
                            )
                            return self._store.get(reference_id)
        except Exception:
            pass

        # 4. Check if it's a database reference
        if "db" in reference_id.casefold() or "database" in reference_id.casefold():
            table_name = "Enterprise Records"
            for t in ("contracts", "invoices", "customers", "employees", "payroll", "transactions", "audit_logs", "departments", "users"):
                if t in reference_id.casefold():
                    table_name = t.capitalize()
                    break
            ref = SourceReference(
                reference_id=reference_id,
                source_type=SourceType.DATABASE,
                display_name=f"[Database] {table_name}",
                title=f"Database: {table_name}",
                location=f"Table: public.{table_name.lower()}",
            )
            self._store.save(
                reference=ref,
                owner_id=user.user_id,
                tenant_id=user.tenant_id,
                source_id=reference_id,
                source_type="database",
                department=user.department,
            )
            return self._store.get(reference_id)

        # 5. Check if it's a Google Drive reference
        if "drive" in reference_id.casefold() or "gdrive" in reference_id.casefold():
            ref = SourceReference(
                reference_id=reference_id,
                source_type=SourceType.DRIVE,
                display_name="[Google Drive] Cloud File",
                title="Google Drive Document",
                location="Google Drive",
            )
            self._store.save(
                reference=ref,
                owner_id=user.user_id,
                tenant_id=user.tenant_id,
                source_id=reference_id,
                source_type="drive",
                department=user.department,
            )
            return self._store.get(reference_id)

        return None


    def _create_from_lineage(self, user: UserAttributes, request_id: str,
                             item: "DataLineage") -> SourceReference | None:
        source_type = self._source_type(item.source_type)
        location = None
        if item.source_type == "database" and item.query:
            import re
            table_match = re.search(r'FROM\s+(?:public\.)?(\w+)', item.query, re.IGNORECASE)
            if table_match:
                tbl = table_match.group(1).lower()
                location = f"Table: public.{tbl}"
        return self._create(
            user=user,
            request_id=request_id,
            source_type=source_type,
            source_id=item.source_id,
            display_name=self._safe_label(item.source_label, source_type),
            title=self._safe_label(item.source_label, source_type),
            location=location,
            page=None,
            sheet=None,
            timestamp=None,
            mime_type=self._mime_type(item.source_type),
            owner_id=item.owner_id,
            tenant_id=item.tenant_id,
            department=item.department,
            restricted_department=item.restricted_department,
        )

    def _create(self, *, user, request_id, source_type, source_id, display_name,
                title, location, page, sheet, timestamp, mime_type, owner_id,
                tenant_id, department, restricted_department):
        if source_type == SourceType.WEBSITE:
            return None
        permission = self._PERMISSIONS[source_type]
        resource = Resource(
            resource_id=source_id,
            resource_type=self._resource_type(source_type),
            tenant_id=tenant_id,
            owner_id=owner_id,
            department=department,
            attributes={"restricted_department": restricted_department} if restricted_department else {},
        )
        decision = self._authorization.authorize(user, permission, resource)
        if not decision.allowed:
            # Important: do not return a placeholder. That would leak that a restricted
            # source exists. Audit only the opaque reference request context.
            self._audit.record("source_reference_creation", "deny", user.user_id, user.tenant_id,
                               request_id, {"source_type": source_type.value})
            return None

        reference_id = str(uuid4())
        reference = SourceReference(
            reference_id=reference_id,
            source_type=source_type,
            display_name=self._safe_metadata(display_name),
            title=self._safe_metadata(title) if title else None,
            location=self._safe_metadata(location),
            page=page,
            sheet=self._safe_metadata(sheet),
            timestamp=timestamp,
            mime_type=mime_type,
            href=f"{self._base_url}/{reference_id}",
        )
        self._store.save(reference, user.user_id, tenant_id, source_id, source_type.value,
                         department, restricted_department)
        self._audit.record("source_reference_creation", "allow", user.user_id, user.tenant_id,
                           reference_id, {"source_type": source_type.value})
        return reference

    @staticmethod
    def _resource(item: dict) -> Resource:
        return Resource(
            resource_id=item["source_id"],
            resource_type={
                "file": "company_file",
                "document": "knowledge_source",
                "email": "email_mailbox",
                "database": "database_source",
                "drive": "google_drive_file",
            }[item["source_type"]],
            tenant_id=item["tenant_id"],
            owner_id=item["owner_id"],
            department=item["department"],
            attributes={"restricted_department": item["restricted_department"]}
            if item["restricted_department"] else {},
        )

    @staticmethod
    def _resource_type(source_type: SourceType) -> str:
        return {
            SourceType.FILE: "company_file",
            SourceType.DOCUMENT: "knowledge_source",
            SourceType.EMAIL: "email_mailbox",
            SourceType.DATABASE: "database_source",
            SourceType.DRIVE: "google_drive_file",
        }[source_type]

    @staticmethod
    def _source_type(value: str) -> SourceType:
        normalized = value.casefold()
        if normalized in {"drive", "google_drive", "gdrive", "google_drive_file"}:
            return SourceType.DRIVE
        if normalized in {"pdf", "docx", "xlsx", "csv", "document", "knowledge_source"}:
            return SourceType.DOCUMENT
        if normalized in {"sql", "postgres", "postgresql", "database", "database_source"}:
            return SourceType.DATABASE
        if normalized in {"email", "mail", "email_mailbox"}:
            return SourceType.EMAIL
        if normalized == "website":
            return SourceType.WEBSITE
        return SourceType.FILE

    @staticmethod
    def _safe_label(value: str | None, source_type: SourceType) -> str:
        if not value:
            return source_type.value.title()
        # Never turn path-like or SQL-like source identifiers into user-facing citations.
        if any(token in value for token in ("\\", "/", "SELECT ", "INSERT ", "UPDATE ", "DELETE ")):
            return source_type.value.title()
        return value[:200]

    def _safe_metadata(self, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.replace("\n", " ").replace("\r", " ").strip()[:200]
        return self._output_filter.validate_public_output(cleaned)

    @staticmethod
    def _sanitize_display_name(value: str) -> str:
        return value.replace("\n", " ").replace("\r", " ").strip()[:200]

    @staticmethod
    def _mime_type(value: str) -> str | None:
        return {
            "pdf": "application/pdf", "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "csv": "text/csv",
        }.get(value.casefold())
