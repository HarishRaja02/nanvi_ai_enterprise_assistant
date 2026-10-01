"""Content-First Company Data Service orchestrator."""
from __future__ import annotations

import hashlib
import logging
import re
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.core.config import settings
from backend.integrations.files.company_data.classification import FOLDER_ROLES, STOPWORDS
from backend.integrations.files.company_data.discovery import build_directory_listing, discover_files, resolve_root
from backend.integrations.files.company_data.extraction import (
    create_default_document_service,
    extract_contract_records_from_files,
    extract_invoice_records_from_files,
)
from backend.integrations.files.company_data.indexing import (
    RAG_RELEVANCE_THRESHOLD,
    CompanyChunk,
    SearchResult,
    chunk_document,
)
from backend.integrations.files.company_data.persistence import get_persisted_folder, set_persisted_folder
from backend.security.authorization import UserAttributes
from backend.security.authorization.rbac import Role
from backend.sources.models import SourceReference, SourceType

logger = logging.getLogger(__name__)


class CompanyDataService:
    _instances: dict[str, CompanyDataService] = {}
    _registry_lock = threading.Lock()

    def __init__(self, root_dir: str | Path | None = None, tenant_id: str = "default") -> None:
        self.tenant_id = str(tenant_id or "default").strip()
        if root_dir is not None:
            self.root = Path(root_dir).resolve()
        else:
            persisted = get_persisted_folder(self.tenant_id)
            if persisted is not None and persisted.exists():
                self.root = persisted
            else:
                self.root = Path("C:/CompanyData")

        self._doc_service = create_default_document_service()
        self._chunks: list[CompanyChunk] = []
        self._indexed_files: dict[str, dict[str, Any]] = {}
        self._file_hashes: dict[str, str] = {}
        self._last_indexed: float = 0.0
        self._index_lock = threading.Lock()

    @classmethod
    def for_tenant(cls, tenant_id: str, root_dir: str | Path | None = None) -> CompanyDataService:
        """Factory method to get or create a per-tenant CompanyDataService instance."""
        t_id = str(tenant_id or "default").strip()
        with cls._registry_lock:
            instance = cls._instances.get(t_id)
            if instance is None:
                persisted = get_persisted_folder(t_id)
                fallback_path = cls._instances["default"].root if "default" in cls._instances else "C:/CompanyData"
                target_path = root_dir if root_dir is not None else (persisted or fallback_path)
                instance = cls(target_path, tenant_id=t_id)
                try:
                    instance.ensure_indexed()
                except Exception as exc:
                    logger.warning("Could not pre-index on for_tenant (%s): %s", t_id, exc)
                cls._instances[t_id] = instance
            elif root_dir is not None:
                target = Path(root_dir).resolve()
                if target != instance.root.resolve():
                    instance.update_root(target)
            return instance

    @classmethod
    def get_instance(cls, root_dir: str | Path | None = None, tenant_id: str = "default") -> CompanyDataService:
        """Backward-compatible entry point delegating to the per-tenant factory."""
        return cls.for_tenant(tenant_id=tenant_id or "default", root_dir=root_dir)

    @classmethod
    def clear_registry(cls) -> None:
        """Clear all cached per-tenant instances (for test isolation)."""
        with cls._registry_lock:
            cls._instances.clear()

    def update_root(self, new_root: str | Path) -> None:
        """Change the company data root directory for this tenant and re-index."""
        new_path = Path(new_root).resolve()
        with self._index_lock:
            self.root = new_path
            self._chunks = []
            self._indexed_files = {}
            self._file_hashes = {}
            self._last_indexed = 0.0
        set_persisted_folder(new_path, tenant_id=self.tenant_id)
        logger.info("CompanyData root for tenant '%s' updated to %s — forcing re-index", self.tenant_id, new_path)
        self.ensure_indexed(force=True)

    @property
    def chunks(self) -> list[CompanyChunk]:
        return self._chunks

    @property
    def files(self) -> list[dict[str, Any]]:
        return list(self._indexed_files.values())

    def _resolve_root(self) -> Path | None:
        return resolve_root(self.root, self.tenant_id)

    def _discover_files(self, base_root: Path) -> list[tuple[str, str, str, Path]]:
        return discover_files(base_root)

    def ensure_indexed(self, force: bool = False) -> None:
        """Scan, extract content, and index all supported files incrementally."""
        with self._index_lock:
            active_root = self._resolve_root()
            if not active_root:
                logger.warning("CompanyData root %s does not exist", self.root)
                return

            now = datetime.now().timestamp()
            if not force and self._chunks and (now - self._last_indexed < 30):
                return

            discovered = self._discover_files(active_root)
            chunks: list[CompanyChunk] = []
            file_summary: dict[str, dict[str, Any]] = {}

            for dept, folder_path, rel_path, file_path in discovered:
                ext = file_path.suffix.casefold()
                try:
                    stat = file_path.stat()
                    mtime = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
                    ctime = datetime.fromtimestamp(stat.st_ctime, tz=timezone.utc)
                    mtime_iso = mtime.isoformat()
                    size_bytes = stat.st_size

                    existing = self._indexed_files.get(rel_path)
                    if not force and existing and existing.get("modified_at") == mtime_iso and existing.get("size_bytes") == size_bytes:
                        file_summary[rel_path] = existing
                        chunks.extend(existing.get("chunks", []))
                        continue

                    data = file_path.read_bytes()
                    chash = hashlib.sha256(data).hexdigest()

                    if not force and existing and self._file_hashes.get(rel_path) == chash:
                        existing["modified_at"] = mtime_iso
                        file_summary[rel_path] = existing
                        chunks.extend(existing.get("chunks", []))
                        continue

                    doc = self._doc_service.parse_bytes(
                        filename=file_path.name,
                        relative_path=rel_path,
                        data=data,
                        modified_at=mtime,
                    )

                    file_chunks = chunk_document(
                        doc=doc,
                        folder=dept,
                        folder_path=folder_path,
                        filename=file_path.name,
                        rel_path=rel_path,
                        full_path=str(file_path),
                        file_type=ext.lstrip("."),
                    )
                    chunks.extend(file_chunks)

                    self._file_hashes[rel_path] = chash
                    file_summary[rel_path] = {
                        "file_id": rel_path,
                        "filename": file_path.name,
                        "file_path": str(file_path),
                        "full_path": str(file_path),
                        "department": dept,
                        "folder": dept,
                        "folder_path": folder_path,
                        "file_type": ext.lstrip("."),
                        "size_bytes": len(data),
                        "text_length": len(doc.text),
                        "preview": doc.text[:250].replace("\n", " ").strip(),
                        "content": doc.text,
                        "chunks": file_chunks,
                        "created_at": ctime.isoformat(),
                        "modified_at": mtime_iso,
                    }
                except Exception as exc:
                    logger.warning("Error indexing %s: %s", rel_path, exc)

            self._chunks = chunks
            self._indexed_files = file_summary
            self._last_indexed = now
            logger.info("Content-first incrementally indexed %d chunks across %d files in %s", len(chunks), len(file_summary), active_root)

    def is_folder_authorized(self, user: UserAttributes, folder_name: str) -> bool:
        """Enforce strict RBAC authorization on company departments while supporting custom user folders."""
        user_roles = {Role(r) if isinstance(r, str) else r for r in user.roles}
        if not user_roles:
            return False

        if Role.SUPERIOR in user_roles:
            return True
        if Role.SUPERVISOR in user_roles:
            return folder_name != "Audit"
        if Role.PROJECT_ENGINEER in user_roles:
            return folder_name in {"Projects", "HR"}
        if Role.EMPLOYEE in user_roles:
            return folder_name == "HR"

        if folder_name == "Finance":
            return bool(user_roles & {Role.CEO, Role.FINANCE, Role.MANAGER, Role.IT_ADMIN})
        if folder_name == "HR":
            if Role.EMPLOYEE in user_roles and getattr(user, "department", None) == "HR":
                return True
            return bool(user_roles & {Role.CEO, Role.HR, Role.MANAGER, Role.IT_ADMIN})
        if folder_name == "Contracts":
            return bool(user_roles & {Role.CEO, Role.FINANCE, Role.MANAGER, Role.IT_ADMIN})

        all_enterprise_roles = {Role.CEO, Role.FINANCE, Role.HR, Role.MANAGER, Role.EMPLOYEE, Role.IT_ADMIN}
        return bool(user_roles & all_enterprise_roles)

    def is_file_authorized(self, user: UserAttributes, folder_name: str, relative_path: str) -> bool:
        if not self.is_folder_authorized(user, folder_name):
            return False
        user_roles = {Role(r) if isinstance(r, str) else r for r in user.roles}
        path = relative_path.casefold()
        if folder_name == "HR":
            sensitive_terms = ("salary", "payroll", "compensation", "performance", "disciplinary", "medical", "tax", "resume", "resumes", "employee_record", "employee_records")
            if any(term in path for term in sensitive_terms):
                return bool(user_roles & {Role.SUPERIOR, Role.SUPERVISOR, Role.CEO, Role.FINANCE, Role.HR, Role.MANAGER, Role.IT_ADMIN})
            if Role.EMPLOYEE in user_roles:
                return any(term in path for term in ("handbook", "benefit", "leave", "holiday", "onboarding", "workplace", "policy"))
        return True

    def search(self, user: UserAttributes, query: str, active_document_id: str | None = None) -> SearchResult:
        """Execute content-first search with RBAC enforcement and relevance validation."""
        if user.tenant_id and self.tenant_id and self.tenant_id != "default" and user.tenant_id != self.tenant_id:
            raise PermissionError(
                f"Tenant access denied: user from tenant '{user.tenant_id}' cannot access company data for tenant '{self.tenant_id}'"
            )
        if not self._chunks:
            self.ensure_indexed()

        query_clean = query.strip()
        if not query_clean:
            return SearchResult(is_exact_match=False, answer_content="")

        q_lower = query_clean.casefold()
        if any(p in q_lower for p in (
            "list all files", "list files", "show all files", "what files do i have",
            "show all documents", "files in companydata", "files in company data",
            "what files are present", "see files", "available files", "file list"
        )):
            visible_files = {
                path: info for path, info in self._indexed_files.items()
                if self.is_file_authorized(user, info["folder"], path)
            }
            return build_directory_listing(visible_files, self.is_folder_authorized, user, q_lower)

        analysis = self._analyze_query(query_clean)

        authorized_chunks = [c for c in self._chunks if self.is_file_authorized(user, c.folder, c.relative_path)]
        if not authorized_chunks or not analysis["keywords"]:
            return SearchResult(is_exact_match=False, answer_content="")

        target_active_id = active_document_id
        if not target_active_id:
            upload_chunks = [c for c in authorized_chunks if "upload" in c.folder.casefold() or "upload" in c.relative_path.casefold()]
            if upload_chunks:
                target_active_id = upload_chunks[-1].filename

        active_chunks: list[CompanyChunk] = []
        if target_active_id:
            active_chunks = [
                c for c in authorized_chunks
                if target_active_id.casefold() in c.filename.casefold()
                or target_active_id.casefold() in c.relative_path.casefold()
                or c.filename.casefold() in target_active_id.casefold()
                or (c.document_id and c.document_id.casefold() in target_active_id.casefold())
            ]

        has_active_doc = bool(active_chunks)
        intent = self._detect_query_intent(query_clean, analysis, has_active_doc, active_chunks)

        is_invoice_list_query = (
            intent not in ("ACTIVE_DOCUMENT", "DOCUMENT_ID")
            and not analysis.get("identifiers")
            and any(w in q_lower for w in (
                "overdue invoice", "overdue invoices", "unpaid invoice", "unpaid invoices",
                "list invoices", "show overdue invoices", "all invoices", "invoices in finance"
            ))
            and not any(w in q_lower for w in ("invoice number", "invoice no", "invoice id", "invoice date", "who is the vendor", "vendor", "total", "cgst", "sgst"))
        )
        if is_invoice_list_query and self.is_folder_authorized(user, "Finance"):
            status_f = "overdue" if "overdue" in q_lower else None
            entity_f = analysis["entities"][0] if analysis.get("entities") else None
            inv_records, inv_sources = self.extract_invoice_records(user, status_filter=status_f, entity_filter=entity_f, limit=10)
            if inv_records:
                heading = "Found the following authorized overdue invoices:" if status_f else "Found the following authorized invoice records in Finance:"
                lines = [heading]
                for r in inv_records[:8]:
                    status_str = f"**{r['status']}**" if "overdue" in r['status'].lower() else r['status']
                    lines.append(f"• **{r['customer']}** — Invoice `{r['id']}` | Amount: **{r['amount']}** | Status: {status_str} | Date: {r['due_date']}")
                if len(inv_records) > 8:
                    lines.append(f"*... and {len(inv_records) - 8} more invoice records available in company records.*")
                return SearchResult(
                    is_exact_match=True,
                    answer_content="\n".join(lines),
                    sources=inv_sources[:5],
                )

        is_contract_lookup = any(w in q_lower for w in ("renewal schedule", "contract renewal", "upcoming renewals", "contract schedule"))
        if is_contract_lookup and intent not in ("ACTIVE_DOCUMENT", "DOCUMENT_ID") and self.is_folder_authorized(user, "Contracts"):
            contract_records, contract_sources = self.extract_contract_records(user, limit=10)
            if contract_records:
                lines = ["Found the following authorized contract renewal schedule:"]
                for r in contract_records[:8]:
                    lines.append(f"• **{r['customer']}** — Contract `{r['id']}` | Type: {r['contract_type']} | Annual Value: **{r['annual_value']}** | Renewal: {r['renewal_date']} | Status: {r['status']}")
                if len(contract_records) > 8:
                    lines.append(f"*... and {len(contract_records) - 8} more contract records available.*")
                return SearchResult(
                    is_exact_match=True,
                    answer_content="\n".join(lines),
                    sources=contract_sources[:5],
                )

        if intent == "ACTIVE_DOCUMENT" and active_chunks:
            candidate_pool = active_chunks
        elif intent == "NAMED_DOCUMENT":
            named_chunks = [
                c for c in authorized_chunks
                if any(k in c.filename.casefold() for k in analysis["keywords"] if len(k) > 3)
            ]
            candidate_pool = named_chunks or authorized_chunks
        else:
            candidate_pool = authorized_chunks

        scored_candidates: list[tuple[float, CompanyChunk]] = []
        rejected_candidates: list[tuple[float, CompanyChunk, str]] = []

        for chunk in candidate_pool:
            score = self._score_chunk_content(chunk, analysis)
            if score <= 0.0:
                continue

            is_valid, reason = self._validate_chunk_relevance_with_reason(chunk, analysis, is_active_doc=(intent == "ACTIVE_DOCUMENT"))
            if not is_valid:
                rejected_candidates.append((score, chunk, reason))
                continue

            effective_thresh = min(15.0, RAG_RELEVANCE_THRESHOLD) if intent == "ACTIVE_DOCUMENT" else RAG_RELEVANCE_THRESHOLD
            if score < effective_thresh:
                rejected_candidates.append((score, chunk, f"Score {score:.1f} < threshold {effective_thresh:.1f}"))
                continue

            scored_candidates.append((score, chunk))

        if not scored_candidates:
            unauthorized_chunks = [c for c in self._chunks if not self.is_file_authorized(user, c.folder, c.relative_path)]
            restricted_matches: list[CompanyChunk] = []
            for chunk in unauthorized_chunks:
                score = self._score_chunk_content(chunk, analysis)
                if score >= RAG_RELEVANCE_THRESHOLD:
                    is_valid, _ = self._validate_chunk_relevance_with_reason(chunk, analysis, is_active_doc=False)
                    if is_valid:
                        restricted_matches.append(chunk)

            if restricted_matches:
                depts = ", ".join(sorted(set(c.folder for c in restricted_matches)))
                user_role_str = ", ".join(sorted(str(r.value if hasattr(r, "value") else r) for r in user.roles)) or "Unassigned"
                return SearchResult(
                    is_exact_match=False,
                    answer_content=(
                        f"Access Restricted: Matching documents were found in the restricted '{depts}' department, "
                        f"but your current user profile ({user_role_str}) is not authorized to access {depts} records. "
                        f"Please sign in with an authorized role (such as Finance, Manager, or CEO) to view this document."
                    ),
                    sources=[],
                )

            return SearchResult(
                is_exact_match=False,
                answer_content="",
                sources=[],
                top_chunks=[],
            )

        scored_candidates.sort(key=lambda x: x[0], reverse=True)
        top_score = scored_candidates[0][0]
        top_file = scored_candidates[0][1].filename

        selected_chunks: list[CompanyChunk] = []
        seen_items = set()

        for score, chunk in scored_candidates:
            item_key = f"{chunk.filename}:{chunk.location}"
            if item_key in seen_items:
                continue

            if chunk.filename == top_file or score >= top_score * 0.45:
                seen_items.add(item_key)
                selected_chunks.append(chunk)
                if len(selected_chunks) >= 4:
                    break

        if not selected_chunks:
            selected_chunks = [scored_candidates[0][1]]

        content_parts = []
        sources: list[SourceReference] = []
        seen_refs = set()

        for chunk in selected_chunks:
            chunk_text = chunk.content.strip()
            if len(chunk_text) > 800:
                lines = chunk_text[:800].splitlines()
                if len(lines) > 2:
                    chunk_text = "\n".join(lines[:-1]) + "\n... [truncated for brevity]"
                else:
                    chunk_text = chunk_text[:800] + "\n... [truncated for brevity]"
            header = f"[{chunk.folder} / {chunk.filename} ({chunk.location})]"
            content_parts.append(f"{header}\n{chunk_text}")

            ref_key = f"{chunk.filename}:{chunk.location}"
            if ref_key not in seen_refs:
                seen_refs.add(ref_key)
                sources.append(SourceReference(
                    reference_id=f"ref-{len(sources)+1}-{chunk.filename.split('.')[0]}",
                    source_type=SourceType.FILE,
                    display_name=f"[{chunk.folder}] {chunk.filename}",
                    title=f"{chunk.filename} ({chunk.location})",
                    location=chunk.full_path,
                    page=chunk.page,
                    sheet=chunk.sheet,
                ))

        if settings.is_development or settings.debug or logger.isEnabledFor(logging.INFO):
            logger.info("=" * 60)
            logger.info("RAG RETRIEVAL DECISION")
            logger.info("QUERY: %r", query_clean)
            logger.info("ACTIVE DOCUMENT: %s", target_active_id or "None")
            logger.info("INTENT: %s", intent)
            logger.info("CANDIDATES SCORED: %d", len(scored_candidates) + len(rejected_candidates))
            for score, chunk in scored_candidates[:5]:
                dec = "ACCEPTED" if chunk in selected_chunks else "FILTERED"
                logger.info("  - [%s] %s (%s) → score: %.1f [%s]", chunk.folder, chunk.filename, chunk.location, score, dec)
            for score, chunk, reason in rejected_candidates[:5]:
                logger.info("  - [%s] %s (%s) → score: %.1f [REJECTED: %s]", chunk.folder, chunk.filename, chunk.location, score, reason)
            logger.info("FINAL SOURCES USED: %s", [s.title for s in sources])
            logger.info("FINAL CHUNKS PASSED TO LLM: %d", len(selected_chunks))
            logger.info("=" * 60)

        return SearchResult(
            is_exact_match=True,
            answer_content="\n\n".join(content_parts),
            sources=sources,
            top_chunks=selected_chunks,
        )

    def search_files(self, user: UserAttributes, query: str) -> SearchResult:
        """Deterministic file discovery: finds matching files by name, path, extension, and content."""
        if user.tenant_id and self.tenant_id and self.tenant_id != "default" and user.tenant_id != self.tenant_id:
            raise PermissionError(
                f"Tenant access denied: user from tenant '{user.tenant_id}' cannot access company data for tenant '{self.tenant_id}'"
            )
        if not self._chunks:
            self.ensure_indexed()

        query_clean = query.strip()
        q_lower = query_clean.casefold()

        if any(p in q_lower for p in (
            "list all files", "list files", "show all files", "what files do i have",
            "show all documents", "files in companydata", "files in company data",
            "what files are present", "see files", "available files", "file list"
        )):
            return build_directory_listing(self._indexed_files, self.is_folder_authorized, user, q_lower)

        analysis = self._analyze_query(query_clean)
        keywords = analysis["keywords"]

        scored_files: list[tuple[float, dict[str, Any]]] = []
        unauthorized_matches: list[dict[str, Any]] = []

        dept_match = None
        for d in FOLDER_ROLES.keys():
            if d.casefold() in q_lower:
                dept_match = d
                break

        for rel_path, info in self._indexed_files.items():
            fn = info["filename"].casefold()
            fn_stem = fn.rsplit(".", 1)[0]
            dept = info["folder"]
            content_lower = info.get("content", "").casefold()

            score = 0.0

            if any(k in fn for k in keywords):
                score += 30.0
            if any(k in fn_stem for k in keywords):
                score += 25.0

            for ident in analysis["identifiers"]:
                if ident in fn:
                    score += 50.0
                elif ident in content_lower:
                    score += 40.0

            matched_kws = 0
            for kw in keywords:
                if kw in fn:
                    matched_kws += 2
                    score += 20.0
                elif kw in content_lower:
                    matched_kws += 1
                    score += 5.0

            if dept_match and dept.casefold() == dept_match.casefold():
                score += 20.0

            if score > 0.0 and (matched_kws > 0 or analysis["identifiers"]):
                if self.is_folder_authorized(user, dept):
                    scored_files.append((score, info))
                else:
                    unauthorized_matches.append(info)

        if not scored_files and unauthorized_matches:
            depts = ", ".join(sorted(set(f["folder"] for f in unauthorized_matches)))
            user_role_str = ", ".join(sorted(str(r.value if hasattr(r, "value") else r) for r in user.roles)) or "Unassigned"
            return SearchResult(
                is_exact_match=False,
                answer_content=(
                    f"Access Restricted: Matching documents were found in the restricted '{depts}' department, "
                    f"but your current user profile ({user_role_str}) is not authorized to access {depts} records. "
                    f"Please sign in with an authorized role (such as Finance, Manager, or CEO) to view this document."
                ),
                sources=[],
            )

        if not scored_files:
            return SearchResult(
                is_exact_match=False,
                answer_content="I couldn't find any documents matching that request in the accessible company folders.",
                sources=[],
            )

        scored_files.sort(key=lambda x: x[0], reverse=True)
        top_files = [f for _, f in scored_files[:5]]

        sources: list[SourceReference] = []
        lines: list[str] = []

        is_ambiguous = len(top_files) > 1 and (
            scored_files[0][0] - scored_files[1][0] < 5.0
            or any(w in q_lower for w in ("latest", "recent", "all", "which", "available"))
        )

        if is_ambiguous:
            lines.append("Found multiple matching documents across company records:\n")
            for idx, f in enumerate(top_files, start=1):
                fn = f["filename"]
                dept = f["folder"]
                path = f.get("full_path") or f.get("file_path", "")
                preview = f.get("preview", "")[:120].strip()
                prev_text = f" — *{preview}*" if preview else ""
                lines.append(f"{idx}. 📁 **[{dept}] {fn}** (`{f['file_id']}`){prev_text}")
                sources.append(SourceReference(
                    reference_id=f"ref-{idx}-{fn.split('.')[0]}",
                    source_type=SourceType.FILE,
                    display_name=f"[{dept}] {fn}",
                    title=fn,
                    location=path,
                ))
            lines.append("\nPlease specify which document or time period you would like details on.")
        else:
            top_file = top_files[0]
            fn = top_file["filename"]
            dept = top_file["folder"]
            ft = top_file["file_type"].upper()
            path = top_file.get("full_path") or top_file.get("file_path", "")
            preview = top_file.get("preview", "")[:250].strip()

            lines.append("Found the following matching document:\n")
            lines.append(f"📁 **[{dept}] {fn}**")
            lines.append(f"• **Location:** `{top_file['file_id']}`")
            lines.append(f"• **Department:** {dept} | **Type:** {ft}")
            if preview:
                lines.append(f"• **Summary:** {preview}")

            sources.append(SourceReference(
                reference_id=f"ref-1-{fn.split('.')[0]}",
                source_type=SourceType.FILE,
                display_name=f"[{dept}] {fn}",
                title=fn,
                location=path,
            ))

            if len(top_files) > 1:
                lines.append("\n*Related documents also found:*")
                for f in top_files[1:3]:
                    lines.append(f"• 📁 **[{f['folder']}] {f['filename']}** (`{f['file_id']}`)")
                    sources.append(SourceReference(
                        reference_id=f"ref-{len(sources)+1}-{f['filename'].split('.')[0]}",
                        source_type=SourceType.FILE,
                        display_name=f"[{f['folder']}] {f['filename']}",
                        title=f['filename'],
                        location=f.get('full_path') or f.get('file_path', ''),
                    ))

        return SearchResult(
            is_exact_match=True,
            answer_content="\n".join(lines),
            sources=sources,
        )

    def _analyze_query(self, query: str) -> dict[str, Any]:
        q_lower = query.casefold()
        tokens = [w.casefold() for w in re.findall(r"\w+", query) if len(w) > 1]
        keywords = [w for w in tokens if w not in STOPWORDS] or tokens

        identifiers = re.findall(r"\b[A-Za-z]{1,5}(?:-[A-Za-z0-9]{2,6})+\b", query)
        amounts = re.findall(r"(?:[₹$€£]\s*[\d,]+(?:\.\d+)?(?:k|m|b)?|\b\d{2,}(?:,\d{3})*(?:\.\d+)?\b)", query, re.IGNORECASE)

        multi_word_entities = re.findall(r"\b([A-Z][a-zA-Z0-9]*(?:\s+[A-Z][a-zA-Z0-9]*)+)\b", query)
        single_entities = re.findall(r"\b([A-Z][a-z0-9]+[A-Z][a-zA-Z0-9]*|[A-Z][a-zA-Z0-9]{3,})\b", query)
        excluded_entities = {
            "what is", "give me", "show me", "find the", "find", "tell", "tell me",
            "which", "where", "please", "invoice", "invoices", "vendor", "vendors", "contract", "contracts",
            "document", "file", "section", "report", "data", "status", "random",
            "show", "list", "give", "view", "check", "search", "fetch", "get", "display",
            "overdue", "paid", "pending", "all", "here", "have", "with", "from", "company", "companies",
            "what", "when", "where", "which", "who", "whom", "whose", "why", "how",
            "tell", "can", "could", "would", "should", "does", "is", "are", "do", "did",
            "now", "about", "information", "details", "mention", "mentioned", "contain", "contains",
            "entire", "available", "dataset", "folder", "folders", "department", "departments", "regardless",
            "employee", "employees", "customer", "customers", "project", "projects", "account", "accounts",
            "task", "tasks", "order", "orders", "agreement", "agreements", "service", "services", "corporation",
        }
        entities = [
            e.casefold() for e in set(multi_word_entities + single_entities)
            if e.casefold() not in excluded_entities and len(e) > 2
        ]

        compound_entities = re.findall(
            r"\b((?:Customer|Employee|Project|Account|Vendor|Contract|Invoice|Task|Order)\s+(\d{1,6}(?:-[A-Za-z0-9]+)*|[A-Za-z]{1,5}-\d{2,6}[A-Za-z0-9-]*|[A-Za-z]+\d+[A-Za-z0-9-]*))\b",
            query,
            re.IGNORECASE,
        )
        for full_comp, code in compound_entities:
            f_norm = full_comp.strip().casefold()
            c_norm = code.strip().casefold()
            if f_norm not in entities:
                entities.append(f_norm)
            if c_norm not in [i.casefold() for i in identifiers]:
                identifiers.append(c_norm)

        acronyms = [w.casefold() for w in re.findall(r"\b[A-Z]{2,6}\b", query) if w.casefold() not in excluded_entities]
        doc_types = {"invoice", "invoices", "contract", "contracts", "resume", "resumes", "policy", "handbook", "report"}
        doc_type_intent = [w for w in keywords if w in doc_types]

        return {
            "query_lower": q_lower,
            "tokens": tokens,
            "keywords": keywords,
            "identifiers": [i.casefold() for i in identifiers],
            "amounts": [a.replace(" ", "").casefold() for a in amounts],
            "entities": entities,
            "acronyms": acronyms,
            "doc_type_intent": doc_type_intent,
        }

    def _score_chunk_content(self, chunk: CompanyChunk, analysis: dict[str, Any]) -> float:
        content_lower = chunk.content.casefold()
        content_score = 0.0

        for entity in analysis["entities"]:
            if entity in content_lower:
                content_score += 35.0

        for acr in analysis["acronyms"]:
            if acr in content_lower:
                content_score += 15.0

        for ident in analysis["identifiers"]:
            if ident in content_lower or (len(ident) >= 3 and re.search(rf"\b{re.escape(ident)}\b", content_lower)):
                content_score += 60.0

        for amt in analysis["amounts"]:
            clean_num = amt.lstrip("₹$€£").replace(",", "")
            if amt in content_lower or (len(clean_num) >= 3 and clean_num in content_lower.replace(",", "")):
                content_score += 15.0

        full_query = analysis["query_lower"]
        if len(full_query) > 5 and full_query in content_lower:
            content_score += 20.0

        matched_keywords = 0
        for kw in analysis["keywords"]:
            matches = re.findall(rf"\b{re.escape(kw)}\b", content_lower)
            count = len(matches)
            if count > 0:
                matched_keywords += 1
                content_score += min(count, 5) * 2.5

        if content_score <= 0.0:
            return 0.0

        if analysis["keywords"]:
            coverage = matched_keywords / len(analysis["keywords"])
            content_score += coverage * 35.0
            if coverage == 1.0:
                content_score += 25.0

        first_line = content_lower.splitlines()[0] if content_lower.splitlines() else ""
        for kw in analysis["keywords"]:
            if len(kw) >= 3 and re.search(rf"(?:^|[|,])\s*{re.escape(kw)}\s*(?:[|,:\n]|$)", first_line):
                content_score += 30.0

        for dt in analysis.get("doc_type_intent", []):
            base_type = dt.rstrip("s")
            if base_type in content_lower or (base_type == "invoice" and "inv-" in content_lower):
                content_score += 30.0

        if any(w in analysis["keywords"] for w in ("vendor", "seller", "supplier", "issuer", "provider")):
            if any(b in content_lower for b in ("pvt. ltd.", "ltd", "inc", "corp", "gstin", "invoice", "billing@")):
                content_score += 35.0

        if any(w in analysis["keywords"] for w in ("number", "num", "id")):
            if any(n in content_lower for n in ("no.", "no :", "no:", "id:", "id :", "inv-", "ctr-", "p-")):
                content_score += 25.0

        filename_lower = chunk.filename.casefold()
        fn_stem = filename_lower.rsplit(".", 1)[0]
        folder_lower = chunk.folder.casefold()
        for kw in analysis["keywords"]:
            if len(kw) >= 3 and (kw in fn_stem or fn_stem in kw):
                content_score += 45.0
            elif kw in filename_lower:
                content_score += 30.0
            if kw in folder_lower:
                content_score += 5.0

        return content_score

    def _validate_chunk_relevance_with_reason(
        self,
        chunk: CompanyChunk,
        analysis: dict[str, Any],
        is_active_doc: bool = False,
    ) -> tuple[bool, str]:
        content_lower = chunk.content.casefold()

        if analysis["identifiers"]:
            if not any(ident in content_lower for ident in analysis["identifiers"]):
                return False, f"Missing required identifier: {analysis['identifiers']}"

        if analysis["entities"] and not analysis["identifiers"]:
            has_entity_mention = any(e in content_lower for e in analysis["entities"])
            has_acronym_mention = any(a in content_lower for a in analysis["acronyms"])
            if not has_entity_mention and not has_acronym_mention:
                return False, f"Missing required entity mention: {analysis['entities']}"

        for dt in analysis.get("doc_type_intent", []):
            base_type = dt.rstrip("s")
            has_doc_type = (
                base_type in content_lower
                or base_type in chunk.folder.casefold()
                or base_type in chunk.relative_path.casefold()
                or (base_type == "invoice" and (any(i.startswith("inv") for i in analysis["identifiers"]) or "invoice" in content_lower or "inv" in chunk.filename.casefold()))
                or (base_type == "contract" and (
                    any(i.startswith("ctr") or i.startswith("cnt") for i in analysis["identifiers"])
                    or "agreement" in content_lower
                    or "agreement" in chunk.filename.casefold()
                    or "nda" in chunk.filename.casefold()
                    or "contract" in chunk.folder.casefold()
                ))
            )
            if not has_doc_type:
                return False, f"Missing document type: {base_type}"

        if not is_active_doc and len(analysis["keywords"]) >= 3 and not analysis["identifiers"] and not analysis["entities"] and not analysis.get("doc_type_intent"):
            matched_kws = sum(1 for kw in analysis["keywords"] if re.search(rf"\b{re.escape(kw)}\b", content_lower))
            coverage = matched_kws / len(analysis["keywords"])
            if coverage < 0.4:
                return False, f"Keyword coverage {coverage:.1%} < 40%"

        filename_lower = chunk.filename.casefold()
        fn_stem = filename_lower.rsplit(".", 1)[0]
        has_kw_in_fn = any(len(kw) >= 3 and (kw in fn_stem or fn_stem in kw or kw in filename_lower) for kw in analysis["keywords"])
        has_kw_in_content = any(re.search(rf"\b{re.escape(kw)}\b", content_lower) for kw in analysis["keywords"])

        if is_active_doc:
            if any(w in analysis["keywords"] for w in ("vendor", "seller", "supplier", "who")) and any(b in content_lower for b in ("pvt. ltd.", "ltd", "inc", "corp", "gstin", "invoice")):
                has_kw_in_content = True
            if any(w in analysis["keywords"] for w in ("number", "num", "id")) and any(n in content_lower for n in ("no.", "no :", "no:", "id:", "inv-")):
                has_kw_in_content = True

        if not has_kw_in_content and not has_kw_in_fn:
            return False, "No keyword match in content or filename"

        return True, "Passed relevance validation"

    def _validate_chunk_relevance(self, chunk: CompanyChunk, analysis: dict[str, Any]) -> bool:
        valid, _ = self._validate_chunk_relevance_with_reason(chunk, analysis)
        return valid

    def _detect_query_intent(
        self,
        query: str,
        analysis: dict[str, Any],
        has_active_doc: bool,
        active_chunks: list[CompanyChunk],
    ) -> str:
        q_lower = query.casefold()

        for rel_path, info in self._indexed_files.items():
            fn = info["filename"].casefold()
            fn_stem = fn.rsplit(".", 1)[0]
            if len(fn_stem) > 4 and (fn in q_lower or fn_stem in q_lower):
                if has_active_doc and fn in [c.filename.casefold() for c in active_chunks]:
                    return "ACTIVE_DOCUMENT"
                return "NAMED_DOCUMENT"

        if analysis["identifiers"]:
            if has_active_doc:
                active_text = " ".join(c.content.casefold() for c in active_chunks)
                if any(ident in active_text for ident in analysis["identifiers"]):
                    return "ACTIVE_DOCUMENT"
            return "DOCUMENT_ID"

        if has_active_doc:
            is_global_metric = any(m in q_lower for m in (
                "july 2026", "august 2026", "q1", "q2", "q3", "q4", "annual budget",
                "company revenue", "subscription revenue in", "enterprise subscription revenue in",
                "smb subscription", "travel policy", "headcount", "engineering sprint"
            ))
            active_text = " ".join(c.content.casefold() for c in active_chunks)
            if is_global_metric and not any(m in active_text for m in ("july 2026", "august 2026", "q1", "annual budget")):
                return "GLOBAL_COMPANY"

            explicit_doc_patterns = (
                "this document", "this file", "this invoice", "attached document",
                "uploaded document", "the document", "the file", "the invoice",
            )
            if any(p in q_lower for p in explicit_doc_patterns) or bool(re.search(r"\b(?:this|it)\b", q_lower)):
                return "ACTIVE_DOCUMENT"

            doc_attr_keywords = (
                "total amount", "total", "subtotal", "invoice number", "invoice no", "invoice id",
                "vendor", "who is the vendor", "who is the seller", "who is the customer", "bill to",
                "cgst", "sgst", "tax amount", "tax", "gstin", "due date", "invoice date",
                "payment terms", "line item", "line items", "place of supply", "amount in words"
            )
            if any(p in q_lower for p in doc_attr_keywords):
                return "ACTIVE_DOCUMENT"

            if any(entity in active_text for entity in analysis.get("entities", [])):
                return "ACTIVE_DOCUMENT"
            clean_q = re.sub(r"^(tell me about|what is|what are|find|show me|describe)\s+", "", q_lower).strip()
            if len(clean_q) > 6 and clean_q in active_text:
                return "ACTIVE_DOCUMENT"

        return "GLOBAL_COMPANY"

    def extract_invoice_records(
        self,
        user: UserAttributes,
        status_filter: str | None = None,
        entity_filter: str | None = None,
        limit: int = 50,
    ) -> tuple[list[dict[str, Any]], list[SourceReference]]:
        """Extract structured invoice records from real company finance documents."""
        if user.tenant_id and self.tenant_id and self.tenant_id != "default" and user.tenant_id != self.tenant_id:
            raise PermissionError(
                f"Tenant access denied: user from tenant '{user.tenant_id}' cannot access company data for tenant '{self.tenant_id}'"
            )
        self.ensure_indexed()
        return extract_invoice_records_from_files(
            indexed_files=self._indexed_files,
            is_folder_authorized=self.is_folder_authorized,
            user=user,
            status_filter=status_filter,
            entity_filter=entity_filter,
            limit=limit,
        )

    def extract_contract_records(
        self,
        user: UserAttributes,
        entity_filter: str | None = None,
        limit: int = 50,
    ) -> tuple[list[dict[str, Any]], list[SourceReference]]:
        """Extract structured contract renewal and agreement records."""
        if user.tenant_id and self.tenant_id and self.tenant_id != "default" and user.tenant_id != self.tenant_id:
            raise PermissionError(
                f"Tenant access denied: user from tenant '{user.tenant_id}' cannot access company data for tenant '{self.tenant_id}'"
            )
        self.ensure_indexed()
        return extract_contract_records_from_files(
            indexed_files=self._indexed_files,
            is_folder_authorized=self.is_folder_authorized,
            user=user,
            entity_filter=entity_filter,
            limit=limit,
        )
