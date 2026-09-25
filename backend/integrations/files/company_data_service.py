"""Content-First Company Data Service for enterprise documents.

Recursively scans department directories down to arbitrary depth, extracts
structured content (text, tables, sheets, pages), builds document metadata,
and executes content-first retrieval with relevance validation.

Fundamental Principle:
Filename and folder names are metadata hints. File content is the source of truth for relevance.
"""
from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from backend.documents.parsers import CSVParser, ExcelParser, PDFParser, TextParser, WordParser
from backend.documents.service import DocumentProcessingService
from backend.security.authorization import UserAttributes
from backend.security.authorization.rbac import Role
from backend.sources.models import SourceReference, SourceType

logger = logging.getLogger(__name__)

STOP_WORDS = frozenset({
    "a", "an", "the", "in", "on", "at", "to", "for", "of", "and", "or", "is",
    "are", "was", "were", "what", "which", "who", "whom", "this", "that", "these",
    "those", "am", "been", "being", "have", "has", "had", "do", "does", "did",
    "can", "could", "should", "would", "may", "might", "must", "shall", "will",
    "our", "my", "your", "their", "its", "from", "by", "with", "about", "into",
    "tell", "me", "show", "give", "find", "get", "please", "nanvi", "company",
    "data", "information", "details", "all", "available", "related",
    "hi", "hello", "hey", "thanks", "thank", "welcome", "section", "folder",
    "file", "files", "document", "documents",
})

# Folder RBAC permissions map
FOLDER_ROLES = {
    "Customers": {Role.CEO, Role.FINANCE, Role.HR, Role.MANAGER, Role.EMPLOYEE, Role.IT_ADMIN},
    "Finance": {Role.CEO, Role.FINANCE, Role.MANAGER, Role.IT_ADMIN},
    "HR": {Role.CEO, Role.HR, Role.MANAGER, Role.IT_ADMIN},
    "Projects": {Role.CEO, Role.FINANCE, Role.HR, Role.MANAGER, Role.EMPLOYEE, Role.IT_ADMIN},
    "Contracts": {Role.CEO, Role.FINANCE, Role.MANAGER, Role.IT_ADMIN},
    "Resumes": {Role.CEO, Role.FINANCE, Role.HR, Role.MANAGER, Role.EMPLOYEE, Role.IT_ADMIN},
    "Uploads": {Role.CEO, Role.FINANCE, Role.HR, Role.MANAGER, Role.EMPLOYEE, Role.IT_ADMIN},
    "General": {Role.CEO, Role.FINANCE, Role.HR, Role.MANAGER, Role.EMPLOYEE, Role.IT_ADMIN},
}

ACTIVE_FOLDER_FILE = Path(__file__).resolve().parent.parent.parent / "storage" / "active_folder.json"


def get_persisted_folder() -> Path | None:
    """Read the last chosen active folder path from persistent storage."""
    try:
        if ACTIVE_FOLDER_FILE.exists():
            import json
            data = json.loads(ACTIVE_FOLDER_FILE.read_text(encoding="utf-8"))
            saved = data.get("path")
            if saved and Path(saved).exists() and Path(saved).is_dir():
                return Path(saved).resolve()
    except Exception as exc:
        logger.warning("Could not read persisted folder path: %s", exc)
    return None


def set_persisted_folder(path: Path | str) -> None:
    """Save active folder path to persistent storage file."""
    try:
        path_str = str(Path(path).resolve())
        ACTIVE_FOLDER_FILE.parent.mkdir(parents=True, exist_ok=True)
        import json
        payload = {
            "path": path_str,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        ACTIVE_FOLDER_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        logger.info("Persisted active company data folder: %s", path)
    except Exception as exc:
        logger.warning("Could not persist active folder path: %s", exc)


@dataclass(frozen=True)
class CompanyChunk:
    chunk_id: str
    folder: str
    filename: str
    relative_path: str
    full_path: str
    file_type: str
    location: str
    content: str
    sheet: str | None = None
    page: int | None = None
    folder_path: str = ""


@dataclass
class SearchResult:
    is_exact_match: bool
    answer_content: str
    sources: list[SourceReference] = field(default_factory=list)
    top_chunks: list[CompanyChunk] = field(default_factory=list)
    recommended_files: list[dict[str, Any]] = field(default_factory=list)


def _classify_department(parts: tuple[str, ...], filename: str, base_root_name: str) -> tuple[str, str]:
    """Determine (department, subfolder) for any file in any directory structure."""
    path_str = "/".join(parts).casefold()
    fn_lower = filename.casefold()
    combined = f"{path_str}/{fn_lower}"

    if not parts:
        return "General", ""

    # Check for department keywords in path or filename
    if any(k in combined for k in ("finance", "invoice", "invoices", "billing", "payable", "receivable", "accounting", "tax", "budget", "expense", "expenses")):
        dept = "Finance"
    elif any(k in combined for k in ("hr", "resumes", "resume", "employees", "employee", "payroll", "headcount", "benefits", "hiring", "recruitment", "handbook")):
        dept = "HR"
    elif any(k in combined for k in ("contract", "contracts", "agreement", "agreements", "nda", "msa", "sla", "renewals", "renewal", "legal")):
        dept = "Contracts"
    elif any(k in combined for k in ("project", "projects", "sprint", "engineering", "tech", "phoenix", "deliverable", "architecture", "audit", "validation")):
        dept = "Projects"
    elif any(k in combined for k in ("customer", "customers", "client", "clients", "sales", "crm", "acme")):
        dept = "Customers"
    elif any(k in combined for k in ("upload", "uploads")):
        dept = "Uploads"
    else:
        # Check if first folder matches standard dept name case-insensitively
        direct_name = parts[0]
        known_map = {d.casefold(): d for d in FOLDER_ROLES.keys()}
        dept = known_map.get(direct_name.casefold(), direct_name)

    subfolder = "/".join(parts[1:]) if len(parts) > 1 else ("/".join(parts) if parts and parts[0] != dept else "")
    return dept, subfolder


class CompanyDataService:
    _instance: CompanyDataService | None = None

    def __init__(self, root_dir: str | Path | None = None) -> None:
        from threading import Lock

        if root_dir is not None:
            self.root = Path(root_dir).resolve()
        else:
            persisted = get_persisted_folder()
            if persisted is not None and persisted.exists():
                self.root = persisted
            else:
                self.root = Path("C:/CompanyData")

        self._doc_service = DocumentProcessingService([
            PDFParser(), WordParser(), ExcelParser(), CSVParser(), TextParser()
        ])
        self._chunks: list[CompanyChunk] = []
        self._indexed_files: dict[str, dict[str, Any]] = {}
        self._file_hashes: dict[str, str] = {}
        self._last_indexed: float = 0.0
        self._index_lock = Lock()
        CompanyDataService._instance = self

    @classmethod
    def get_instance(cls, root_dir: str | Path | None = None) -> CompanyDataService:
        if cls._instance is None:
            persisted = get_persisted_folder()
            target_path = root_dir if root_dir is not None else (persisted or "C:/CompanyData")
            cls._instance = CompanyDataService(target_path)
            try:
                cls._instance.ensure_indexed()
            except Exception as exc:
                logger.warning("Could not pre-index on get_instance: %s", exc)
        elif root_dir is not None:
            target = Path(root_dir).resolve()
            if target != cls._instance.root.resolve():
                cls._instance.update_root(target)
        return cls._instance

    def update_root(self, new_root: str | Path) -> None:
        """Change the company data root directory at runtime and re-index.

        Clears the existing index and forces a full scan of the new location.
        Thread-safe: acquires the index lock before making changes.
        """
        new_path = Path(new_root).resolve()
        with self._index_lock:
            self.root = new_path
            self._chunks = []
            self._indexed_files = {}
            self._file_hashes = {}
            self._last_indexed = 0.0
        set_persisted_folder(new_path)
        logger.info("CompanyData root updated to %s — forcing re-index", new_path)
        self.ensure_indexed(force=True)

    @property
    def chunks(self) -> list[CompanyChunk]:
        return self._chunks

    @property
    def files(self) -> list[dict[str, Any]]:
        return list(self._indexed_files.values())

    def _resolve_root(self) -> Path | None:
        if self.root.exists() and self.root.is_dir():
            return self.root
        persisted = get_persisted_folder()
        if persisted and persisted.exists() and persisted.is_dir():
            self.root = persisted
            return persisted
        fallback = Path(__file__).resolve().parent.parent.parent.parent / "CompanyData"
        if fallback.exists() and fallback.is_dir():
            return fallback
        test_doc_fallback = Path(__file__).resolve().parent.parent.parent.parent / "test_doc"
        if test_doc_fallback.exists() and test_doc_fallback.is_dir():
            return test_doc_fallback
        return None

    def _discover_files(self, base_root: Path) -> list[tuple[str, str, str, Path]]:
        """Recursively scan root directory down to arbitrary subfolder depth.

        Returns list of (department, folder_path, rel_path, full_file_path).
        Supports ANY directory structure: flat folders, custom subfolders, or standard enterprise departments.
        """
        discovered: list[tuple[str, str, str, Path]] = []
        if not base_root.exists() or not base_root.is_dir():
            return discovered

        for current_root, dir_names, file_names in os.walk(base_root, followlinks=False):
            # Exclude hidden directories and symlinks
            dir_names[:] = [
                d for d in dir_names
                if not d.startswith(".") and not (Path(current_root) / d).is_symlink()
            ]

            rel_curr = Path(current_root).relative_to(base_root)
            parts = rel_curr.parts

            for name in file_names:
                if name.startswith(".") or name.startswith("~$"):
                    continue
                ext = Path(name).suffix.casefold()
                if ext not in {".pdf", ".docx", ".xlsx", ".csv", ".txt", ".md", ".pptx"}:
                    continue

                full_path = Path(current_root) / name
                dept, subfolder = _classify_department(parts, name, base_root.name)

                rel_parts = [dept]
                if subfolder:
                    rel_parts.append(subfolder)
                rel_parts.append(name)
                rel_path = "/".join(rel_parts)

                discovered.append((dept, subfolder, rel_path, full_path))

        return discovered

    def ensure_indexed(self, force: bool = False) -> None:
        """Scan, extract content, and index all supported files incrementally.
        
        Uses mtime and SHA-256 content hashes to skip unchanged files, avoiding
        expensive re-reads and re-parsing. Uses thread locking to prevent concurrent indexing.
        """
        import hashlib
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
            active_paths = set()

            for dept, folder_path, rel_path, file_path in discovered:
                active_paths.add(rel_path)
                ext = file_path.suffix.casefold()
                try:
                    stat = file_path.stat()
                    mtime = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
                    ctime = datetime.fromtimestamp(stat.st_ctime, tz=timezone.utc)
                    mtime_iso = mtime.isoformat()
                    size_bytes = stat.st_size

                    # Check if file is unchanged: same mtime, same size, existing chunks
                    existing = self._indexed_files.get(rel_path)
                    if not force and existing and existing.get("modified_at") == mtime_iso and existing.get("size_bytes") == size_bytes:
                        file_summary[rel_path] = existing
                        chunks.extend(existing.get("chunks", []))
                        continue

                    # Read file content and compute hash
                    data = file_path.read_bytes()
                    chash = hashlib.sha256(data).hexdigest()

                    if not force and existing and self._file_hashes.get(rel_path) == chash:
                        # Content is unchanged, just update timestamp
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

                    file_chunks = self._chunk_document(
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

    def _chunk_document(
        self,
        doc,
        folder: str,
        folder_path: str,
        filename: str,
        rel_path: str,
        full_path: str,
        file_type: str,
    ) -> list[CompanyChunk]:
        chunks: list[CompanyChunk] = []
        text = doc.text.strip()
        if not text:
            return chunks

        # PDF with pages
        if file_type == "pdf" and "[Page " in text:
            pages = re.split(r"(?m)^\[Page (\d+)\]\n", text)
            if len(pages) > 1:
                idx = 1
                while idx < len(pages):
                    page_num = int(pages[idx])
                    content = pages[idx + 1].strip() if idx + 1 < len(pages) else ""
                    if content:
                        chunks.append(CompanyChunk(
                            chunk_id=f"{rel_path}:page-{page_num}",
                            folder=folder,
                            filename=filename,
                            relative_path=rel_path,
                            full_path=full_path,
                            file_type=file_type,
                            location=f"Page {page_num}",
                            content=content,
                            page=page_num,
                            folder_path=folder_path,
                        ))
                    idx += 2
                return chunks

        # Excel with sheets
        if file_type == "xlsx" and "[Sheet " in text:
            sheets = re.split(r"(?m)^\[Sheet (.+?)\]\n", text)
            if len(sheets) > 1:
                idx = 1
                while idx < len(sheets):
                    sheet_name = sheets[idx].strip()
                    content = sheets[idx + 1].strip() if idx + 1 < len(sheets) else ""
                    if content:
                        chunks.append(CompanyChunk(
                            chunk_id=f"{rel_path}:sheet-{sheet_name}",
                            folder=folder,
                            filename=filename,
                            relative_path=rel_path,
                            full_path=full_path,
                            file_type=file_type,
                            location=f"Sheet: {sheet_name}",
                            content=content,
                            sheet=sheet_name,
                            folder_path=folder_path,
                        ))
                    idx += 2
                return chunks

        # DOCX / CSV / Text: split by logical paragraphs or table sections
        sections = [s.strip() for s in text.split("\n\n") if len(s.strip()) > 20]
        if not sections:
            sections = [text]

        for i, sec in enumerate(sections, start=1):
            chunks.append(CompanyChunk(
                chunk_id=f"{rel_path}:sec-{i}",
                folder=folder,
                filename=filename,
                relative_path=rel_path,
                full_path=full_path,
                file_type=file_type,
                location=f"Section {i}",
                content=sec,
                folder_path=folder_path,
            ))
        return chunks

    def is_folder_authorized(self, user: UserAttributes, folder_name: str) -> bool:
        """Enforce strict RBAC authorization on company departments while supporting custom user folders."""
        user_roles = {Role(r) if isinstance(r, str) else r for r in user.roles}
        if not user_roles:
            return False

        # Strictly restrict sensitive departments
        if folder_name == "Finance":
            return bool(user_roles & {Role.CEO, Role.FINANCE, Role.MANAGER, Role.IT_ADMIN})
        if folder_name == "HR":
            if Role.EMPLOYEE in user_roles and getattr(user, "department", None) == "HR":
                return True
            return bool(user_roles & {Role.CEO, Role.HR, Role.MANAGER, Role.IT_ADMIN})
        if folder_name == "Contracts":
            return bool(user_roles & {Role.CEO, Role.FINANCE, Role.MANAGER, Role.IT_ADMIN})

        # For standard general departments, root files, or custom user folders:
        # All authenticated enterprise roles are authorized to access.
        all_enterprise_roles = {Role.CEO, Role.FINANCE, Role.HR, Role.MANAGER, Role.EMPLOYEE, Role.IT_ADMIN}
        return bool(user_roles & all_enterprise_roles)

    def search(self, user: UserAttributes, query: str) -> SearchResult:
        """Execute content-first search with RBAC enforcement and relevance validation."""
        if not self._chunks:
            self.ensure_indexed()

        query_clean = query.strip()
        if not query_clean:
            return SearchResult(is_exact_match=False, answer_content="")

        # Check for explicit file listing / browsing request
        q_lower = query_clean.casefold()
        if any(p in q_lower for p in (
            "list all files", "list files", "show all files", "what files do i have",
            "show all documents", "files in companydata", "files in company data",
            "what files are present", "see files", "available files", "file list"
        )):
            return self._build_directory_listing(user, q_lower)

        # Extract search features: entities, identifiers, amounts, keywords
        analysis = self._analyze_query(query_clean)

        # Content-First Invoice search optimization: send concise required fields (company, overdue status, amount)
        # to prevent exceeding LLM rate limits on free-tier providers while preserving source references
        is_invoice_lookup = (
            any(w in q_lower for w in ("invoice", "invoices", "overdue invoice", "overdue bill", "unpaid invoice", "billing", "bill", "bills"))
            or ("overdue" in q_lower and any(w in q_lower for w in ("finance", "payment", "customer", "vendor", "account", "due", "money")))
        )
        if is_invoice_lookup and self.is_folder_authorized(user, "Finance"):
            status_f = "overdue" if "overdue" in q_lower else None
            entity_f = analysis["entities"][0] if analysis.get("entities") else (
                analysis["identifiers"][0] if analysis.get("identifiers") else None
            )
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

        # Content-First Contract search optimization
        is_contract_lookup = any(w in q_lower for w in ("renewal schedule", "contract renewal", "upcoming renewals", "contract schedule"))
        if is_contract_lookup and self.is_folder_authorized(user, "Contracts"):
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

        # 1. Filter chunks by authorized department
        authorized_chunks = [c for c in self._chunks if self.is_folder_authorized(user, c.folder)]
        if not authorized_chunks or not analysis["keywords"]:
            return SearchResult(is_exact_match=False, answer_content="")

        # 2. Score candidate chunks purely based on actual content relevance
        scored_candidates: list[tuple[float, CompanyChunk]] = []
        for chunk in authorized_chunks:
            score = self._score_chunk_content(chunk, analysis)
            if score > 0.0:
                scored_candidates.append((score, chunk))

        if not scored_candidates or not [c for _, c in scored_candidates if self._validate_chunk_relevance(c, analysis)]:
            # Check if matching content exists in restricted departments that the user is not authorized to access
            unauthorized_chunks = [c for c in self._chunks if not self.is_folder_authorized(user, c.folder)]
            restricted_matches: list[CompanyChunk] = []
            for chunk in unauthorized_chunks:
                score = self._score_chunk_content(chunk, analysis)
                if score > 0.0 and self._validate_chunk_relevance(chunk, analysis):
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
            return SearchResult(is_exact_match=False, answer_content="")

        # 3. Relevance Validation: prune false positives
        # If an explicit entity was queried (e.g. "ABC Company"), candidate chunks must actually mention it
        validated_candidates: list[tuple[float, CompanyChunk]] = []
        for score, chunk in scored_candidates:
            if self._validate_chunk_relevance(chunk, analysis):
                validated_candidates.append((score, chunk))

        if not validated_candidates:
            return SearchResult(is_exact_match=False, answer_content="")

        # 4. Content Reranking & Cross-Department / Cross-File Candidate Selection
        validated_candidates.sort(key=lambda x: x[0], reverse=True)

        # Group by department first to ensure multi-department coverage (Contracts, Customers, Finance, HR, Projects)
        dept_groups: dict[str, list[tuple[float, CompanyChunk]]] = {}
        for score, chunk in validated_candidates:
            dept_groups.setdefault(chunk.folder, []).append((score, chunk))

        selected_chunks: list[CompanyChunk] = []
        seen_filenames = set()

        # If multiple departments match, take the top file from each department first
        if len(dept_groups) > 1:
            for dept, group in dept_groups.items():
                for score, chunk in group:
                    item_key = f"{chunk.filename}:{chunk.sheet}" if chunk.sheet else chunk.filename
                    if item_key not in seen_filenames:
                        seen_filenames.add(item_key)
                        selected_chunks.append(chunk)
                        break
                if len(selected_chunks) >= 4:
                    break

        # Fill remaining slots with top candidates across all files
        if len(selected_chunks) < 4:
            for score, chunk in validated_candidates:
                item_key = f"{chunk.filename}:{chunk.sheet}" if chunk.sheet else chunk.filename
                if item_key not in seen_filenames:
                    seen_filenames.add(item_key)
                    selected_chunks.append(chunk)
                    if len(selected_chunks) >= 4:
                        break

        # If still fewer than 4 files, allow secondary chunk from top matching files
        if len(selected_chunks) < 4:
            for score, chunk in validated_candidates:
                if chunk not in selected_chunks:
                    selected_chunks.append(chunk)
                    if len(selected_chunks) >= 4:
                        break

        selected_chunks = selected_chunks[:4]

        content_parts = []
        sources: list[SourceReference] = []
        seen_refs = set()

        for chunk in selected_chunks:
            # Compact chunk text to prevent hitting LLM rate limits
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

        return SearchResult(
            is_exact_match=True,
            answer_content="\n\n".join(content_parts),
            sources=sources,
            top_chunks=selected_chunks,
        )

    def search_files(self, user: UserAttributes, query: str) -> SearchResult:
        """Deterministic file discovery: finds matching files by name, path, extension, and content.
        
        Enforces strict RBAC before returning results. Returns structured file locations with 0 LLM calls.
        """
        if not self._chunks:
            self.ensure_indexed()

        query_clean = query.strip()
        q_lower = query_clean.casefold()

        # Check for directory listing requests
        if any(p in q_lower for p in (
            "list all files", "list files", "show all files", "what files do i have",
            "show all documents", "files in companydata", "files in company data",
            "what files are present", "see files", "available files", "file list"
        )):
            return self._build_directory_listing(user, q_lower)

        analysis = self._analyze_query(query_clean)
        keywords = analysis["keywords"]

        # 1. Score all indexed files based on filename, path, department, and content relevance
        scored_files: list[tuple[float, dict[str, Any]]] = []
        unauthorized_matches: list[dict[str, Any]] = []

        # Determine target department if explicitly named
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

            # Exact or stem match
            if any(k in fn for k in keywords):
                score += 30.0
            if any(k in fn_stem for k in keywords):
                score += 25.0

            # Specific identifier in filename or content
            for ident in analysis["identifiers"]:
                if ident in fn:
                    score += 50.0
                elif ident in content_lower:
                    score += 40.0

            # Query keywords in content
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

            # Content relevance check: must match at least one significant keyword or identifier
            if score > 0.0 and (matched_kws > 0 or analysis["identifiers"]):
                if self.is_folder_authorized(user, dept):
                    scored_files.append((score, info))
                else:
                    unauthorized_matches.append(info)

        # 2. Check for unauthorized access
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

        # Sort by score descending
        scored_files.sort(key=lambda x: x[0], reverse=True)
        top_files = [f for _, f in scored_files[:5]]

        # Build clean deterministic file discovery response
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

        # Tokenize
        tokens = [w.casefold() for w in re.findall(r"\w+", query) if len(w) > 1]
        keywords = [w for w in tokens if w not in STOP_WORDS] or tokens

        # Detect identifiers (e.g., P-001-005, P-002-010, CTR-01-005, C-001-000, E-001-005, T-001-005, TX-01-0000, INV-00001, CUST-1005, CNT-2023-01, SVC-0005, VND-0007)
        identifiers = re.findall(r"\b[A-Za-z]{1,5}(?:-[A-Za-z0-9]{2,6})+\b", query)

        # Detect currency / numerical values (e.g., ₹75,000, 75,000, $450k, 85,000)
        amounts = re.findall(r"(?:[₹$€£]\s*[\d,]+(?:\.\d+)?(?:k|m|b)?|\b\d{2,}(?:,\d{3})*(?:\.\d+)?\b)", query, re.IGNORECASE)

        # Extract entity phrases: multi-word ("ABC Company") and PascalCase/Capitalized ("CloudNova", "BluePeak")
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

        # Detect compound enterprise entities with codes/numbers (e.g., Customer 001, Customer 015, Employee 1005, Project P-001-005)
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

        # Check for standalone uppercase acronyms/entities (e.g. ABC, XYZ, CEO)
        acronyms = [w.casefold() for w in re.findall(r"\b[A-Z]{2,6}\b", query) if w.casefold() not in excluded_entities]

        # Detect explicit document type intent (e.g. user asks for invoice, contract, resume)
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
        """Calculate content relevance score.

        Rule: Filename and folder names do NOT qualify a chunk.
        If chunk content does not match the query content, score is 0.0.
        """
        content_lower = chunk.content.casefold()
        content_score = 0.0

        # 1. Exact entity / company name in content (+35.0)
        for entity in analysis["entities"]:
            if entity in content_lower:
                content_score += 35.0

        # Standalone acronyms/entities in content (+15.0)
        for acr in analysis["acronyms"]:
            if acr in content_lower:
                content_score += 15.0

        # 2. Specific identifiers in content (+60.0 priority bonus for exact match)
        for ident in analysis["identifiers"]:
            if ident in content_lower or (len(ident) >= 3 and re.search(rf"\b{re.escape(ident)}\b", content_lower)):
                content_score += 60.0

        # 3. Currency / amounts in content (+15.0)
        for amt in analysis["amounts"]:
            clean_num = amt.lstrip("₹$€£").replace(",", "")
            if amt in content_lower or (len(clean_num) >= 3 and clean_num in content_lower.replace(",", "")):
                content_score += 15.0

        # 4. Multi-word phrase in content (+20.0)
        full_query = analysis["query_lower"]
        if len(full_query) > 5 and full_query in content_lower:
            content_score += 20.0

        # 5. Keyword density in content (enforce whole-word boundaries)
        matched_keywords = 0
        for kw in analysis["keywords"]:
            matches = re.findall(rf"\b{re.escape(kw)}\b", content_lower)
            count = len(matches)
            if count > 0:
                matched_keywords += 1
                content_score += min(count, 5) * 2.5

        # If chunk content matches none of the key query features, score is strictly 0.0
        if content_score <= 0.0:
            return 0.0

        # Reward full keyword coverage across terms
        if analysis["keywords"]:
            coverage = matched_keywords / len(analysis["keywords"])
            content_score += coverage * 35.0
            if coverage == 1.0:
                content_score += 25.0

        # 6. Table / Column header match bonus (+30.0)
        # If a query attribute (e.g. budget, salary, amount, value, status, role) is in the first line table header
        first_line = content_lower.splitlines()[0] if content_lower.splitlines() else ""
        for kw in analysis["keywords"]:
            if len(kw) >= 3 and re.search(rf"(?:^|[|,])\s*{re.escape(kw)}\s*(?:[|,:\n]|$)", first_line):
                content_score += 30.0

        # Document type intent match bonus
        for dt in analysis.get("doc_type_intent", []):
            base_type = dt.rstrip("s")
            if base_type in content_lower or (base_type == "invoice" and "inv-" in content_lower):
                content_score += 30.0

        # Filename/stem match bonus (+45.0)
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

    def _validate_chunk_relevance(self, chunk: CompanyChunk, analysis: dict[str, Any]) -> bool:
        """Validate that the candidate chunk actually relates to the question intent.

        If the user asked for a specific entity (e.g. "ABC Company"), the chunk's content
        must actually mention that entity or its core distinguishing token.
        A file called `ABC_Company.pdf` containing only `Customer: XYZ Company` fails this check.
        """
        content_lower = chunk.content.casefold()

        # If specific identifiers requested, content must contain at least one
        if analysis["identifiers"]:
            if not any(ident in content_lower for ident in analysis["identifiers"]):
                return False

        # If specific entity requested (and no identifier was requested), content must contain entity or acronym
        if analysis["entities"] and not analysis["identifiers"]:
            has_entity_mention = any(e in content_lower for e in analysis["entities"])
            has_acronym_mention = any(a in content_lower for a in analysis["acronyms"])
            if not has_entity_mention and not has_acronym_mention:
                return False

        # If explicit document type requested (e.g. "invoice"), chunk must match that document type
        for dt in analysis.get("doc_type_intent", []):
            base_type = dt.rstrip("s")
            has_doc_type = (
                base_type in content_lower
                or (base_type == "invoice" and (any(i.startswith("inv") for i in analysis["identifiers"]) or "invoice" in content_lower))
                or (base_type == "contract" and any(i.startswith("ctr") or i.startswith("cnt") for i in analysis["identifiers"]))
            )
            if not has_doc_type:
                return False

        # Require at least one non-stopword keyword in chunk content (whole-word match) or filename match
        filename_lower = chunk.filename.casefold()
        fn_stem = filename_lower.rsplit(".", 1)[0]
        has_kw_in_fn = any(len(kw) >= 3 and (kw in fn_stem or fn_stem in kw or kw in filename_lower) for kw in analysis["keywords"])
        has_kw_in_content = any(re.search(rf"\b{re.escape(kw)}\b", content_lower) for kw in analysis["keywords"])
        if not has_kw_in_content and not has_kw_in_fn:
            return False

        return True

    def _build_directory_listing(self, user: UserAttributes, q_lower: str) -> SearchResult:
        """Handle explicit requests to list or browse available files."""
        authorized_files = {
            p: info for p, info in self._indexed_files.items()
            if self.is_folder_authorized(user, info["folder"])
        }

        # Filter by department if mentioned
        for dept in list(FOLDER_ROLES.keys()) + [info["folder"] for info in self._indexed_files.values()]:
            if dept.casefold() in q_lower:
                authorized_files = {p: info for p, info in authorized_files.items() if info["folder"].casefold() == dept.casefold()}
                break

        lines = ["Here are the authorized company files you have access to:"]
        sources: list[SourceReference] = []
        for idx, (rel_path, info) in enumerate(list(authorized_files.items())[:15], start=1):
            folder = info["folder"]
            fn = info["filename"]
            ft = info["file_type"].upper()
            sub = f" ({info['folder_path']})" if info.get("folder_path") else ""
            lines.append(f"{idx}. 📁 **[{folder}] {fn}**`{sub}` (`{ft}`)")
            sources.append(SourceReference(
                reference_id=f"dir-{idx}-{fn.split('.')[0]}",
                source_type=SourceType.FILE,
                display_name=f"[{folder}] {fn}",
                title=f"[{folder}] {fn}",
                location=info.get("full_path") or info.get("file_path", ""),
            ))

        return SearchResult(
            is_exact_match=True,
            answer_content="\n".join(lines),
            sources=sources,
        )

    def extract_invoice_records(
        self,
        user: UserAttributes,
        status_filter: str | None = None,
        entity_filter: str | None = None,
        limit: int = 50,
    ) -> tuple[list[dict[str, Any]], list[SourceReference]]:
        """Extract structured invoice records from real company finance documents.
        
        Extracts only required concise fields (Company, Invoice ID, Amount, Status, Date)
        to protect against LLM rate limits on free-tier providers while preserving provenance.
        """
        self.ensure_indexed()

        records: list[dict[str, Any]] = []
        sources: list[SourceReference] = []
        seen_ids: set[str] = set()
        seen_refs: set[str] = set()

        for rel_path, info in self._indexed_files.items():
            folder = info.get("folder", "General")
            if not self.is_folder_authorized(user, folder):
                continue
            filename = info["filename"]
            content = info.get("content", "")
            if "invoice" not in filename.lower() and "invoice" not in content.lower() and "payment" not in filename.lower() and "billing" not in filename.lower():
                continue

            # 1. Check for tabular rows (e.g. CSV or spreadsheet schedules with pipe |)
            table_lines = [l.strip() for l in content.split("\n") if "|" in l]
            if len(table_lines) >= 2:
                header_line = table_lines[0].casefold()
                if "invoice" in header_line or "vendor" in header_line or "amount" in header_line:
                    raw_headers = [h.strip().casefold() for h in table_lines[0].split("|")]
                    for line in table_lines[1:]:
                        parts = [p.strip() for p in line.split("|")]
                        if len(parts) != len(raw_headers):
                            continue
                        row_dict = dict(zip(raw_headers, parts))
                        inv_id = None
                        amount = None
                        status = "Pending"
                        due_date = ""
                        comp_name = ""
                        vendor = ""
                        for h, val in row_dict.items():
                            if "invoice id" in h or h == "inv" or (not inv_id and val.upper().startswith("INV-")):
                                inv_id = val
                            elif any(k in h for k in ("amount", "total", "cost", "price")):
                                amount = val
                            elif "status" in h:
                                status = val
                            elif any(k in h for k in ("due", "date")):
                                if not due_date or "due" in h:
                                    due_date = val
                            elif any(k in h for k in ("customer", "client", "account")):
                                comp_name = val
                            elif "vendor" in h:
                                vendor = val

                        if inv_id and amount:
                            if inv_id in seen_ids:
                                continue
                            if status_filter and status_filter.casefold() not in status.casefold():
                                continue
                            if entity_filter:
                                ef = entity_filter.casefold()
                                if ef not in comp_name.casefold() and ef not in vendor.casefold() and ef not in inv_id.casefold():
                                    continue
                            seen_ids.add(inv_id)
                            display_comp = comp_name or vendor or "Enterprise Client"
                            records.append({
                                "id": inv_id,
                                "customer": display_comp,
                                "vendor": vendor,
                                "amount": amount,
                                "status": status,
                                "due_date": due_date,
                                "file_path": rel_path,
                            })
                            if rel_path not in seen_refs:
                                seen_refs.add(rel_path)
                                sources.append(SourceReference(
                                    reference_id=f"ref-inv-{inv_id}",
                                    source_type=SourceType.FILE,
                                    display_name=f"[Finance] {filename}",
                                    title=f"{filename} - {inv_id}",
                                    location=info.get("full_path") or info.get("file_path", ""),
                                ))
                            if len(records) >= limit:
                                break

            if len(records) >= limit:
                break

            # 2. Key-value formatted documents (PDF, DOCX, TXT)
            inv_id_m = re.search(r"(?:Invoice\s*(?:ID|#|No|Number)?|INV)\s*[:\n\-]\s*([A-Za-z0-9-]+)", content, re.IGNORECASE)
            total_m = re.search(r"(?:Total\s*Amount|Amount\s*Due|Grand\s*Total|Total|Amount|Balance)\s*[:\n\-]\s*([^\n|]+)", content, re.IGNORECASE)
            if not inv_id_m or not total_m:
                continue

            inv_id = inv_id_m.group(1).strip()
            if inv_id in seen_ids:
                continue

            vendor_m = re.search(r"(?:Vendor\s*(?:Name)?|Provider|From|Billed\s*By)\s*[:\n\-]\s*([^\n|]+)", content, re.IGNORECASE)
            customer_m = re.search(r"(?:Customer\s*(?:Name)?|Client|Bill\s*To|Billed\s*To|Company)\s*[:\n\-]\s*([^\n|]+)", content, re.IGNORECASE)
            status_m = re.search(r"(?:Payment\s*Status|Status)\s*[:\n\-]\s*([^\n|]+)", content, re.IGNORECASE)
            date_m = re.search(r"(?:Due\s*Date|Invoice\s*Date|Date)\s*[:\n\-]\s*([^\n|]+)", content, re.IGNORECASE)

            vendor = vendor_m.group(1).strip() if vendor_m else ""
            customer = customer_m.group(1).strip() if customer_m else ""
            status = status_m.group(1).strip() if status_m else ("Overdue" if "overdue" in content.lower() else "Pending")
            date_str = date_m.group(1).strip() if date_m else ""
            total_raw = total_m.group(1).strip()

            if status_filter and status_filter.casefold() not in status.casefold():
                continue

            if entity_filter:
                ef = entity_filter.casefold()
                if ef not in customer.casefold() and ef not in vendor.casefold() and ef not in inv_id.casefold():
                    continue

            seen_ids.add(inv_id)
            comp_name = customer if customer and customer != "Synthetic" else (vendor or "Enterprise Client")

            records.append({
                "id": inv_id,
                "customer": comp_name,
                "vendor": vendor,
                "amount": total_raw,
                "status": status,
                "due_date": date_str,
                "file_path": rel_path,
            })

            if rel_path not in seen_refs:
                seen_refs.add(rel_path)
                sources.append(SourceReference(
                    reference_id=f"ref-inv-{inv_id}",
                    source_type=SourceType.FILE,
                    display_name=f"[Finance] {filename}",
                    title=f"{filename} - {inv_id}",
                    location=info.get("full_path") or info.get("file_path", ""),
                ))

            if len(records) >= limit:
                break

        if not status_filter:
            records.sort(key=lambda r: 0 if "overdue" in r["status"].lower() else 1)

        return records, sources

    def extract_contract_records(
        self,
        user: UserAttributes,
        entity_filter: str | None = None,
        limit: int = 50,
    ) -> tuple[list[dict[str, Any]], list[SourceReference]]:
        """Extract structured contract renewal and agreement records."""
        self.ensure_indexed()

        records: list[dict[str, Any]] = []
        sources: list[SourceReference] = []
        seen_ids: set[str] = set()

        for rel_path, info in self._indexed_files.items():
            folder = info.get("folder", "General")
            if not self.is_folder_authorized(user, folder):
                continue
            filename = info["filename"]
            content = info.get("content", "")

            if "renewal" in filename.lower() or "schedule" in filename.lower() or "register" in filename.lower():
                lines = [l.strip() for l in content.split("\n") if "|" in l]
                for line in lines:
                    parts = [p.strip() for p in line.split("|")]
                    if len(parts) >= 5 and parts[0].upper().startswith(("CNT-", "CTR-")):
                        cid = parts[0]
                        if cid in seen_ids:
                            continue
                        if entity_filter:
                            ef = entity_filter.casefold()
                            if not any(ef in p.casefold() for p in parts[:4]):
                                continue
                        seen_ids.add(cid)
                        records.append({
                            "id": cid,
                            "customer": parts[1] if len(parts) > 1 else "",
                            "contract_type": parts[2] if len(parts) > 2 else "Standard Agreement",
                            "annual_value": parts[3] if len(parts) > 3 else "N/A",
                            "renewal_date": parts[4] if len(parts) > 4 else "",
                            "status": parts[6] if len(parts) > 6 else "Active",
                            "file_path": rel_path,
                        })

                if records:
                    sources.append(SourceReference(
                        reference_id=f"ref-contract-{filename.split('.')[0]}",
                        source_type=SourceType.FILE,
                        display_name=f"[Contracts] {filename}",
                        title=f"{filename}",
                        location=info.get("full_path") or info.get("file_path", ""),
                    ))
                    break

        return records[:limit], sources

