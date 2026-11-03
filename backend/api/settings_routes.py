"""API routes for runtime application settings (e.g., company data folder)."""

from __future__ import annotations

import logging
import os
import re
import string
import sys
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from backend.core.config import settings
from backend.security.dependencies import get_current_user
from backend.security.models import UserIdentity

logger = logging.getLogger(__name__)

router = APIRouter(tags=["settings"])


class RuntimeSettingsResponse(BaseModel):
    app_mode: str
    app_name: str
    is_production: bool
    allows_synthetic_data: bool
    demo_banner: bool
    features: dict[str, bool]


@router.get("/settings/runtime")
async def get_runtime_settings() -> RuntimeSettingsResponse:
    """Return public-safe runtime metadata and capabilities."""
    return RuntimeSettingsResponse(
        app_mode=settings.app_mode,
        app_name=settings.app_name,
        is_production=settings.is_production,
        allows_synthetic_data=settings.allows_synthetic_data,
        demo_banner=not settings.is_production,
        features={
            "database_configured": bool(settings.database_url or settings.supabase_database_url),
            "email_configured": bool(settings.gmail_refresh_token or settings.google_client_id),
            "llm_configured": bool(settings.groq_api_key),
            "company_folder_configured": True,
        },
    )


class CompanyFolderResponse(BaseModel):
    path: str
    exists: bool
    folder_count: int
    file_count: int


class CompanyFolderUpdateRequest(BaseModel):
    path: str


class CompanyFolderUpdateResponse(BaseModel):
    status: str
    path: str
    exists: bool
    folder_count: int
    file_count: int
    indexed_files: int
    message: str


def _is_admin(user: UserIdentity) -> bool:
    """Check if the user has permission to manage or select company folders."""
    roles_normalized = {
        (r.value if hasattr(r, "value") else str(r)).lower().replace(" ", "").replace("_", "").replace("-", "")
        for r in user.roles
    }
    return bool(roles_normalized.intersection({"superior", "supervisor", "ceo", "finance", "itadmin", "admin", "administrator"}))


def _get_filesystem_root_entries() -> list[dict[str, str | bool]]:
    """Return approved root entries for browsing. Strictly excludes /, C:\\, and /var/task."""
    entries: list[dict[str, str | bool]] = []
    known_paths: set[str] = set()

    for name, configured_path in getattr(settings, "company_file_roots", ()):
        try:
            configured_root = Path(configured_path).expanduser().resolve()
            norm = str(configured_root).replace("\\", "/").lower()
            if "/var/task" in norm or "var/task" in norm:
                continue
            normalized_path = str(configured_root).casefold()
            if configured_root.is_dir() and normalized_path not in known_paths:
                entries.append({"name": name, "path": str(configured_root), "is_dir": True})
                known_paths.add(normalized_path)
        except (OSError, RuntimeError, ValueError):
            continue

    # Also include folders connected via the Local Agent BAT file
    try:
        from backend.local_agent.service import get_local_agent_service
        status_data = get_local_agent_service().get_status("enterprise-tenant", "default")
        for f in status_data.connected_folders:
            norm = f.folder_path.casefold()
            if norm not in known_paths:
                entries.append({"name": f.display_name or f.folder_path, "path": f.folder_path, "is_dir": True})
                known_paths.add(norm)
    except Exception:
        pass

    return entries


def _resolve_requested_path(path: str) -> Path:
    """Resolve a path and enforce storage root confinement.
    Strictly forbids /var/task/CompanyData and path traversal outside roots.
    """
    clean = os.path.expandvars(path.strip())
    norm_clean = clean.replace("\\", "/").lower()

    if "/var/task" in norm_clean or "var/task" in norm_clean:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Server path /var/task/CompanyData is disabled. Folders can only be accessed through the Nanvi Local Agent BAT file.",
        )

    # Check against system directories
    system_blacklists = ["/etc", "/sys", "/usr", "/bin", "/sbin"]
    if os.name == "nt":
        system_blacklists.extend(["c:\\windows", "c:\\program files", "c:\\program files (x86)"])
    for blk in system_blacklists:
        if norm_clean.startswith(blk.replace("\\", "/").lower()):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Requested path is outside approved storage roots.",
            )

    try:
        p = Path(clean).expanduser().resolve()
    except (OSError, RuntimeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid folder path.",
        ) from exc

    # Enforce confinement to configured roots if configured
    configured_roots = getattr(settings, "company_file_roots", ())
    if configured_roots:
        is_inside = False
        for _, cr in configured_roots:
            try:
                cr_resolved = Path(cr).expanduser().resolve()
                if p == cr_resolved or p.is_relative_to(cr_resolved):
                    is_inside = True
                    break
            except Exception:
                continue
        if not is_inside:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Requested path is outside approved storage roots.",
            )

    return p


def _folder_stats(folder_path: str) -> dict:
    """Return basic stats about a folder quickly without recursive freeze."""
    if not folder_path or "/var/task" in folder_path.replace("\\", "/").lower():
        return {"exists": False, "folder_count": 0, "file_count": 0}
    p = Path(folder_path)
    if not p.exists() or not p.is_dir():
        return {"exists": False, "folder_count": 0, "file_count": 0}

    folder_count = 0
    file_count = 0
    try:
        # Avoid unbounded deep traversal of hidden/massive folders (like venv or node_modules)
        for root, dirs, files in os.walk(folder_path):
            dirs[:] = [
                d for d in dirs
                if not d.startswith(".")
                and d.lower() not in ("node_modules", "venv", ".git", "__pycache__", "dist", "build", "coverage", ".pytest_cache")
            ]
            folder_count += len(dirs)
            file_count += sum(1 for f in files if not f.startswith(".") and not f.startswith("~$"))
            if file_count > 25000:
                break
    except (PermissionError, OSError):
        pass
    return {"exists": True, "folder_count": folder_count, "file_count": file_count}


@router.get("/settings/company-folder")
async def get_company_folder(
    user: UserIdentity = Depends(get_current_user),
) -> CompanyFolderResponse:
    """Return the current company data folder path from the connected BAT file local agent.
    Never returns /var/task/CompanyData.
    """
    from backend.local_agent.service import get_local_agent_service

    service = get_local_agent_service()
    tenant_id = getattr(user, "tenant_id", None) or "enterprise-tenant"
    user_id = str(getattr(user, "subject", None) or getattr(user, "user_id", "default"))
    status_data = service.get_status(tenant_id, user_id)

    if status_data.connected_folders:
        primary = status_data.connected_folders[0]
        return CompanyFolderResponse(
            path=primary.folder_path,
            exists=True,
            folder_count=len(status_data.connected_folders),
            file_count=status_data.total_files,
        )

    # Check if a custom valid directory was set (e.g. in test suite)
    from backend.integrations.files.company_data_service import CompanyDataService
    cds = CompanyDataService.for_tenant(user.tenant_id)
    root_str = str(cds.root).replace("\\", "/")
    if root_str and "/var/task" not in root_str.lower() and cds.root.exists() and cds.root.is_dir() and len(cds.files) > 0:
        stats = _folder_stats(str(cds.root))
        return CompanyFolderResponse(
            path=str(cds.root),
            exists=stats["exists"],
            folder_count=stats["folder_count"],
            file_count=len(cds.files),
        )

    return CompanyFolderResponse(
        path="",
        exists=False,
        folder_count=0,
        file_count=0,
    )


@router.put("/settings/company-folder")
async def update_company_folder(
    body: CompanyFolderUpdateRequest,
    user: UserIdentity = Depends(get_current_user),
) -> CompanyFolderUpdateResponse:
    """Update or register a company data folder. Restricted to admin roles.
    Blocks /var/task/CompanyData and registers local paths with the BAT file agent.
    """
    if not _is_admin(user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required to update company folder.",
        )

    new_path = body.path.strip()
    if not new_path:
        return CompanyFolderUpdateResponse(
            status="error",
            path="",
            exists=False,
            folder_count=0,
            file_count=0,
            indexed_files=0,
            message="Folder path cannot be empty.",
        )

    norm_new = new_path.replace("\\", "/").lower()
    if "/var/task" in norm_new or "var/task" in norm_new or norm_new == "companydata":
        return CompanyFolderUpdateResponse(
            status="error",
            path=new_path,
            exists=False,
            folder_count=0,
            file_count=0,
            indexed_files=0,
            message="Server path /var/task/CompanyData is disabled. Folders can only be accessed through the Nanvi Local Agent BAT file on your Windows computer.",
        )

    p = _resolve_requested_path(new_path)

    # Forward to Local Agent Service so the Windows BAT file picks it up
    from backend.local_agent.service import get_local_agent_service
    local_svc = get_local_agent_service()
    tenant_id = getattr(user, "tenant_id", None) or "enterprise-tenant"
    user_id = str(getattr(user, "subject", None) or getattr(user, "user_id", "default"))
    local_svc.request_folder(tenant_id, user_id, str(p))

    # Also update CompanyDataService if it's a locally existing directory (e.g. tests)
    from backend.integrations.files.company_data_service import CompanyDataService
    service = CompanyDataService.for_tenant(user.tenant_id)
    if p.exists() and p.is_dir():
        service.update_root(str(p))

    stats = _folder_stats(str(p))
    agent_status = local_svc.get_status(tenant_id, user_id)
    file_count = agent_status.total_files or len(service.files) or stats["file_count"]

    logger.info("Company data folder registered as %s by user %s", p, user.subject)

    return CompanyFolderUpdateResponse(
        status="ok",
        path=str(p),
        exists=True,
        folder_count=len(agent_status.connected_folders) or 1,
        file_count=file_count,
        indexed_files=file_count,
        message=f"Company data folder registered for Nanvi Local Agent BAT file. Path: {p}",
    )


@router.post("/settings/company-folder/browse")
async def browse_directory(
    body: CompanyFolderUpdateRequest,
    user: UserIdentity = Depends(get_current_user),
) -> dict:
    """Browse approved directories for admin folder selection.
    Strictly forbids browsing /var/task or raw system roots.
    """
    if not _is_admin(user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required to browse company folders.",
        )

    target = body.path.strip()

    if not target:
        return {"path": "", "parent": None, "entries": _get_filesystem_root_entries()}

    p = _resolve_requested_path(target)

    if not p.exists() or not p.is_dir():
        return {"path": "", "entries": [], "error": "Directory not found."}

    entries: list[dict[str, str | bool]] = []
    try:
        for entry in p.iterdir():
            try:
                resolved_entry = entry.resolve()
                norm = str(resolved_entry).replace("\\", "/").lower()
                if "/var/task" in norm or "var/task" in norm:
                    continue
                if resolved_entry.is_dir():
                    entries.append({
                        "name": entry.name,
                        "path": str(resolved_entry),
                        "is_dir": True,
                    })
            except (OSError, RuntimeError):
                continue
        entries.sort(key=lambda entry: str(entry["name"]).casefold())
    except (PermissionError, OSError):
        return {"path": "", "entries": [], "error": "Permission denied."}

    parent_path = str(p.parent) if p.parent != p else None
    return {"path": str(p), "parent": parent_path, "entries": entries}

