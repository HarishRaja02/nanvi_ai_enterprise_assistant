"""API routes for runtime application settings (e.g., company data folder)."""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from backend.security.dependencies import get_current_user
from backend.security.models import UserIdentity

logger = logging.getLogger(__name__)

router = APIRouter(tags=["settings"])


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

    service = CompanyDataService.get_instance()
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
    """Update the company data folder to a new path and re-index."""
    from backend.integrations.files.company_data_service import CompanyDataService

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

    p = Path(new_path)
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

    service = CompanyDataService.get_instance()
    service.update_root(new_path)

    stats = _folder_stats(new_path)
    indexed = len(service.files)

    logger.info("Company data folder updated to %s by user %s (indexed %d files)", new_path, user.subject, indexed)

    return CompanyFolderUpdateResponse(
        status="ok",
        path=new_path,
        exists=stats["exists"],
        folder_count=stats["folder_count"],
        file_count=stats["file_count"],
        indexed_files=indexed,
        message=f"Company data folder updated to {new_path}. {indexed} files indexed.",
    )


@router.post("/settings/company-folder/browse")
async def browse_directory(
    body: CompanyFolderUpdateRequest,
    user: UserIdentity = Depends(get_current_user),
) -> dict:
    """List subdirectories of a given path for the folder browser."""
    target = body.path.strip()
    if not target:
        # Return drive roots on Windows, or / on Unix
        import platform
        if platform.system() == "Windows":
            import string
            drives = []
            for letter in string.ascii_uppercase:
                drive = f"{letter}:\\"
                if Path(drive).exists():
                    drives.append({"name": drive, "path": drive, "is_dir": True})
            return {"path": "", "entries": drives}
        else:
            return {"path": "/", "entries": [{"name": "/", "path": "/", "is_dir": True}]}

    p = Path(target)
    if not p.exists() or not p.is_dir():
        return {"path": target, "entries": [], "error": "Directory not found"}

    entries = []
    try:
        for entry in sorted(p.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower())):
            if entry.name.startswith("."):
                continue
            if entry.is_dir():
                entries.append({
                    "name": entry.name,
                    "path": str(entry),
                    "is_dir": True,
                })
    except PermissionError:
        return {"path": target, "entries": [], "error": "Permission denied"}

    return {"path": target, "parent": str(p.parent) if p.parent != p else None, "entries": entries}
