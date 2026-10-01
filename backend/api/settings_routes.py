"""API routes for runtime application settings (e.g., company data folder)."""

from __future__ import annotations

import logging
import os
import string
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
    """Check if the user has an administrative role."""
    roles_normalized = {
        r.lower().replace(" ", "").replace("_", "").replace("-", "")
        for r in user.roles
    }
    return bool(roles_normalized.intersection({"superior", "supervisor", "ceo", "finance", "itadmin", "admin", "administrator"}))


def _get_filesystem_root_entries() -> list[dict[str, str | bool]]:
    """Return starting locations for browsing the backend machine's filesystem."""
    entries: list[dict[str, str | bool]] = []
    if os.name == "nt":
        for drive in string.ascii_uppercase:
            root = Path(f"{drive}:\\")
            try:
                if root.is_dir():
                    entries.append({"name": f"{drive}:\\", "path": str(root), "is_dir": True})
            except OSError:
                continue
    else:
        root = Path("/")
        entries.append({"name": "Filesystem root ( / )", "path": str(root), "is_dir": True})

    known_paths = {str(entry["path"]).casefold() for entry in entries}
    for name, configured_path in settings.company_file_roots:
        try:
            configured_root = Path(configured_path).expanduser().resolve()
            normalized_path = str(configured_root).casefold()
            if configured_root.is_dir() and normalized_path not in known_paths:
                entries.append({"name": name, "path": str(configured_root), "is_dir": True})
                known_paths.add(normalized_path)
        except (OSError, RuntimeError, ValueError):
            continue
    return entries


def _resolve_requested_path(path: str) -> Path:
    """Resolve a user-selected path without restricting it to configured roots."""
    try:
        return Path(path).expanduser().resolve()
    except (OSError, RuntimeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid folder path.",
        ) from exc


def _folder_stats(folder_path: str) -> dict:
    """Return basic stats about a folder."""
    p = Path(folder_path)
    if not p.exists() or not p.is_dir():
        return {"exists": False, "folder_count": 0, "file_count": 0}

    folder_count = 0
    file_count = 0
    try:
        for entry in p.iterdir():
            if entry.name.startswith("."):
                continue
            if entry.is_dir():
                folder_count += 1
            elif entry.is_file():
                file_count += 1
    except PermissionError:
        pass
    return {"exists": True, "folder_count": folder_count, "file_count": file_count}


@router.get("/settings/company-folder")
async def get_company_folder(
    user: UserIdentity = Depends(get_current_user),
) -> CompanyFolderResponse:
    """Return the current company data folder path."""
    from backend.integrations.files.company_data_service import CompanyDataService

    service = CompanyDataService.for_tenant(user.tenant_id)
    current_path = str(service.root)
    stats = _folder_stats(current_path)
    file_cnt = len(service.files) if service.files else stats["file_count"]
    return CompanyFolderResponse(
        path=current_path,
        exists=stats["exists"],
        folder_count=stats["folder_count"],
        file_count=file_cnt,
    )


@router.put("/settings/company-folder")
async def update_company_folder(
    body: CompanyFolderUpdateRequest,
    user: UserIdentity = Depends(get_current_user),
) -> CompanyFolderUpdateResponse:
    """Update the company data folder to a new path and re-index. Restricted to admin roles."""
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

    p = _resolve_requested_path(new_path)
    if not p.exists():
        return CompanyFolderUpdateResponse(
            status="error",
            path=new_path,
            exists=False,
            folder_count=0,
            file_count=0,
            indexed_files=0,
            message=f"Folder does not exist: {new_path}",
        )

    if not p.is_dir():
        return CompanyFolderUpdateResponse(
            status="error",
            path=new_path,
            exists=True,
            folder_count=0,
            file_count=0,
            indexed_files=0,
            message=f"Path is not a directory: {new_path}",
        )

    from backend.integrations.files.company_data_service import CompanyDataService
    service = CompanyDataService.for_tenant(user.tenant_id)
    service.update_root(str(p))

    stats = _folder_stats(str(p))
    indexed = len(service.files)

    logger.info("Company data folder updated to %s by user %s (indexed %d files)", p, user.subject, indexed)

    return CompanyFolderUpdateResponse(
        status="ok",
        path=str(p),
        exists=stats["exists"],
        folder_count=stats["folder_count"],
        file_count=stats["file_count"],
        indexed_files=indexed,
        message=f"Company data folder updated to {p}. {indexed} files indexed.",
    )


@router.post("/settings/company-folder/browse")
async def browse_directory(
    body: CompanyFolderUpdateRequest,
    user: UserIdentity = Depends(get_current_user),
) -> dict:
    """List subdirectories anywhere on the backend filesystem for admin folder selection."""
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

