"""File system discovery and directory listing traversal for enterprise company data."""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Callable

from backend.integrations.files.company_data.classification import FOLDER_ROLES, _classify_department
from backend.integrations.files.company_data.indexing import SearchResult
from backend.integrations.files.company_data.persistence import get_persisted_folder
from backend.security.authorization import UserAttributes
from backend.sources.models import SourceReference, SourceType

logger = logging.getLogger(__name__)


def resolve_root(current_root: Path, tenant_id: str) -> Path | None:
    """Resolve the active root directory for company documents."""
    if current_root.exists() and current_root.is_dir():
        return current_root
    persisted = get_persisted_folder(tenant_id)
    if persisted and persisted.exists() and persisted.is_dir():
        return persisted
    fallback = Path(__file__).resolve().parent.parent.parent.parent / "CompanyData"
    if fallback.exists() and fallback.is_dir():
        return fallback
    test_doc_fallback = Path(__file__).resolve().parent.parent.parent.parent / "test_doc"
    if test_doc_fallback.exists() and test_doc_fallback.is_dir():
        return test_doc_fallback
    return None


def discover_files(base_root: Path) -> list[tuple[str, str, str, Path]]:
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


def build_directory_listing(
    indexed_files: dict[str, dict[str, Any]],
    is_folder_authorized: Callable[[UserAttributes, str], bool],
    user: UserAttributes,
    q_lower: str,
) -> SearchResult:
    """Handle explicit requests to list or browse available files."""
    authorized_files = {
        p: info for p, info in indexed_files.items()
        if is_folder_authorized(user, info["folder"])
    }

    # Filter by department if mentioned
    for dept in list(FOLDER_ROLES.keys()) + [info["folder"] for info in indexed_files.values()]:
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
