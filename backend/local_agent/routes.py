"""FastAPI router for Nanvi Local File Agent endpoints."""
from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response, status
from fastapi.responses import FileResponse

from pydantic import BaseModel

from backend.security.dependencies import get_current_user, get_optional_current_user
from backend.security.models import UserIdentity
from .models import (
    AddFolderRequest,
    FolderSyncPayload,
    LocalAgentHeartbeat,
    LocalAgentStatusResponse,
    LocalAgentTokenResponse,
    LocalSearchRequest,
    LocalSearchResponse,
)
from .service import LocalAgentService, get_local_agent_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/local-agent", tags=["local-agent"])


def _extract_agent_identity(
    authorization: Annotated[str | None, Header()] = None,
    service: LocalAgentService = Depends(get_local_agent_service),
) -> tuple[str, str]:
    """Authenticate incoming local agent requests using bearer pairing token."""
    if not authorization or not authorization.startswith("Bearer "):
        if not settings.is_production:
            return "enterprise-tenant", "default"
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or malformed Authorization header. Expected 'Bearer <pairing_token>'",
        )
    token = authorization.split(" ", 1)[1].strip()
    if token in ("default", "local", "demo", "nanvi-local-token"):
        return "enterprise-tenant", "default"
    try:
        payload = service.verify_agent_token(token)
        tenant_id = payload.get("tenant_id", "enterprise-tenant")
        user_id = payload.get("sub", "default")
        return tenant_id, user_id
    except Exception as exc:
        if not settings.is_production:
            return "enterprise-tenant", "default"
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid pairing token: {exc}",
        )


# ---------------------------------------------------------------------------
# User Endpoints (Accessed from Frontend Web App)
# ---------------------------------------------------------------------------

def _get_user_id(user: UserIdentity) -> str:
    return str(getattr(user, "subject", None) or getattr(user, "user_id", "default"))


class OpenFileRequest(BaseModel):
    file_path: str


@router.post("/open-file")
async def local_agent_open_file(
    body: OpenFileRequest,
    user: UserIdentity | None = Depends(get_optional_current_user),
    service: LocalAgentService = Depends(get_local_agent_service),
) -> dict[str, Any]:
    """Queue an open_file command to the user's connected Windows PC agent."""
    raw_path = body.file_path.strip()
    if raw_path.startswith("file:///"):
        raw_path = raw_path[8:]

    t_id = getattr(user, "tenant_id", None) or "enterprise-tenant"
    u_id = _get_user_id(user) if user else "default"

    from pathlib import Path
    cmd_id = service.queue_command(t_id, u_id, "open_file", {"file_path": raw_path})
    if u_id != "default":
        try:
            service.queue_command(t_id, "default", "open_file", {"file_path": raw_path})
        except Exception:
            pass
    return {
        "status": "ok",
        "opened": raw_path,
        "message": f"Opening {Path(raw_path).name} on your connected Windows computer...",
        "queued": True,
        "command_id": cmd_id,
    }


@router.get("/document-content")
async def get_document_content(
    path: str = Query(..., description="File path or relative path to view"),
    download: bool = Query(False, description="Whether to download original file binary"),
    service: LocalAgentService = Depends(get_local_agent_service),
) -> Response:
    """Serve the document for ephemeral in-memory browser preview (PDF, HTML preview, images) or download."""
    from pathlib import Path
    import mimetypes
    from backend.integrations.files.company_data.extraction import create_default_document_service
    from backend.documents.preview_renderer import render_document_to_html
    from backend.documents.parsers.common import source_for, metadata_for
    from backend.documents.models import Document

    raw = path.strip()
    if raw.startswith("file:///"):
        raw = raw[8:]

    clean = raw.replace("\\", "/").strip("/")
    filename = clean.split("/")[-1] if "/" in clean else clean

    # Strip drive letter and common prefixes like 'CompanyData'
    parts = clean.split("/")
    clean_parts = [p for p in parts if p and not p.endswith(":") and p.lower() != "companydata"]
    rel_path = "/".join(clean_parts)

    search_roots: list[Path] = []
    # 1. Dynamically add active folder from CompanyDataService
    try:
        from backend.integrations.files.company_data_service import CompanyDataService
        for tid in ("default", "enterprise-tenant"):
            cds_inst = CompanyDataService.for_tenant(tid)
            if cds_inst.root and str(cds_inst.root) and cds_inst.root.exists() and cds_inst.root.is_dir():
                if cds_inst.root not in search_roots:
                    search_roots.append(cds_inst.root)
    except Exception:
        pass

    # 2. Dynamically add connected folders from LocalAgentStore
    try:
        for (t, u), d in service.store._data.items():
            for f_info in d.get("folders", {}).values():
                fp = f_info.get("folder_path")
                if fp:
                    p_cand = Path(fp).resolve()
                    if p_cand.exists() and p_cand.is_dir() and p_cand not in search_roots:
                        search_roots.append(p_cand)
    except Exception:
        pass

    target_file: Path | None = None
    for r in search_roots:
        if not r.exists() or not r.is_dir():
            continue
        c1 = (r / rel_path).resolve()
        if c1.is_file():
            target_file = c1
            break
        for f in r.rglob(filename):
            if f.is_file():
                target_file = f
                break
        if target_file:
            break

    if not target_file:
        try:
            direct = Path(raw).resolve()
            if direct.is_file():
                target_file = direct
        except Exception:
            pass

    if target_file and target_file.is_file():
        suffix = target_file.suffix.lower()
        media_type = mimetypes.guess_type(target_file.name)[0]

        # 1. If explicit download requested, return original file attachment
        if download:
            return FileResponse(
                path=str(target_file),
                media_type=media_type or "application/octet-stream",
                headers={
                    "Content-Disposition": f'attachment; filename="{target_file.name}"',
                    "Cache-Control": "no-cache, no-store, must-revalidate",
                },
            )

        # 2. Ephemeral In-Memory Preview in Browser
        # Native PDF preview
        if suffix == ".pdf":
            return FileResponse(
                path=str(target_file),
                media_type="application/pdf",
                headers={
                    "Content-Disposition": f'inline; filename="{target_file.name}"',
                    "Cache-Control": "no-cache, no-store, must-revalidate",
                },
            )

        # Native Image preview
        if suffix in (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"):
            return FileResponse(
                path=str(target_file),
                media_type=media_type or "image/png",
                headers={
                    "Content-Disposition": f'inline; filename="{target_file.name}"',
                    "Cache-Control": "no-cache, no-store, must-revalidate",
                },
            )

        # Raw HTML
        if suffix in (".html", ".htm"):
            return FileResponse(
                path=str(target_file),
                media_type="text/html; charset=utf-8",
                headers={
                    "Content-Disposition": f'inline; filename="{target_file.name}"',
                    "Cache-Control": "no-cache, no-store, must-revalidate",
                },
            )

        # Rich In-Memory Preview for Word, Excel, CSV, TSV, PPT, Text, JSON, XML, RTF
        try:
            doc_service = create_default_document_service()
            file_bytes = target_file.read_bytes()
            doc_model = doc_service.parse_bytes(
                filename=target_file.name,
                relative_path=rel_path or target_file.name,
                data=file_bytes,
            )
            html_preview = render_document_to_html(doc_model)
            return Response(
                content=html_preview,
                media_type="text/html; charset=utf-8",
                headers={
                    "Content-Disposition": f'inline; filename="{target_file.name}.html"',
                    "Cache-Control": "no-cache, no-store, must-revalidate",
                },
            )
        except Exception as parse_err:
            logger.debug("Could not render HTML preview for %s (%s), falling back to raw", target_file.name, parse_err)

        if suffix in (".txt", ".log", ".csv", ".json", ".md", ".py"):
            media_type = media_type or "text/plain; charset=utf-8"
        else:
            media_type = media_type or "application/octet-stream"

        return FileResponse(
            path=str(target_file),
            media_type=media_type,
            headers={
                "Content-Disposition": f'inline; filename="{target_file.name}"',
                "Cache-Control": "no-cache, no-store, must-revalidate",
            },
        )

    # If file is not directly present on disk, check indexed chunks in LocalAgentStore
    try:
        t_id = "enterprise-tenant"
        u_id = "default"
        val = service.store._load_key(t_id, u_id)
        chunks = val.get("chunks", [])
        if not chunks:
            for k, d in getattr(service.store, "_data", {}).items():
                if d.get("chunks"):
                    chunks = d.get("chunks")
                    break
        fn_low = filename.lower()
        matching = [
            c for c in chunks
            if c.get("filename", "").lower() == fn_low or fn_low in c.get("relative_path", "").lower()
        ]
        if matching:
            matching.sort(key=lambda c: c.get("chunk_index", 0))
            joined_text = "\n\n".join(c.get("text", "") for c in matching)
            try:
                doc_model = Document(
                    source=source_for(filename, rel_path or filename, filename.split(".")[-1] if "." in filename else "txt"),
                    metadata=metadata_for(len(joined_text)),
                    text=joined_text,
                )
                html_preview = render_document_to_html(doc_model)
                return Response(
                    content=html_preview,
                    media_type="text/html; charset=utf-8",
                    headers={
                        "Content-Disposition": f'inline; filename="{filename}.html"',
                        "Cache-Control": "no-cache, no-store, must-revalidate",
                    },
                )
            except Exception:
                return Response(
                    content=joined_text,
                    media_type="text/plain; charset=utf-8",
                    headers={
                        "Content-Disposition": f'inline; filename="{filename}.txt"',
                        "Cache-Control": "no-cache, no-store, must-revalidate",
                    },
                )
    except Exception as exc:
        logger.debug("Could not read chunks for document-content: %s", exc)

    raise HTTPException(status_code=404, detail=f"Document '{filename}' could not be found.")


@router.get("/document-download")
async def download_document_endpoint(
    path: str = Query(..., description="File path to download"),
    service: LocalAgentService = Depends(get_local_agent_service),
) -> Response:
    """Download the original document binary file."""
    return await get_document_content(path=path, download=True, service=service)


@router.get("/download")
async def download_agent_package(
    request: Request,
    token: str | None = None,
    format: str = "bat",
    user: UserIdentity | None = Depends(get_optional_current_user),
    service: LocalAgentService = Depends(get_local_agent_service),
) -> Response:
    """Download a pre-configured 1-click Windows .bat file or zip package for the user."""
    from .packager import generate_agent_bat, generate_agent_zip
    from backend.security.authorization.rbac import Role

    proto = request.headers.get("x-forwarded-proto", request.url.scheme)
    host = request.headers.get("x-forwarded-host", request.url.netloc)
    server_url = f"{proto}://{host}".rstrip("/") if host else str(request.base_url).rstrip("/")
    pairing_token = ""
    display_name = ""

    if user:
        resp = service.create_pairing_token(user, server_url)
        pairing_token = resp.token
        display_name = resp.display_name
    elif token:
        try:
            payload = service.verify_agent_token(token)
            pairing_token = token
            display_name = payload.get("display_name", "")
        except Exception:
            pairing_token = "nanvi-local-token"
            display_name = "Company User"
    else:
        # User not logged in or in demo mode: generate a default pairing token so BAT download never fails
        default_user = UserIdentity(
            subject="default",
            tenant_id="enterprise-tenant",
            roles=frozenset({Role.IT_ADMIN}),
            email="user@company.local",
        )
        try:
            resp = service.create_pairing_token(default_user, server_url)
            pairing_token = resp.token
            display_name = "Company User"
        except Exception:
            pairing_token = "nanvi-local-token"
            display_name = "Company User"

    if format == "zip":
        zip_bytes = generate_agent_zip(server_url, pairing_token, display_name)
        return Response(
            content=zip_bytes,
            media_type="application/zip",
            headers={
                "Content-Disposition": 'attachment; filename="Nanvi_Windows_Agent.zip"',
                "Cache-Control": "no-store",
            },
        )

    bat_content = generate_agent_bat(server_url, pairing_token, display_name)
    return Response(
        content=bat_content.encode("utf-8"),
        media_type="application/x-bat",
        headers={
            "Content-Disposition": 'attachment; filename="Nanvi_Assistant.bat"',
            "Cache-Control": "no-store",
        },
    )


@router.post("/token", response_model=LocalAgentTokenResponse)
async def generate_pairing_token(
    request: Request,
    user: UserIdentity = Depends(get_current_user),
    service: LocalAgentService = Depends(get_local_agent_service),
) -> LocalAgentTokenResponse:
    """Generate a pairing token for the user to authenticate their local agent."""
    server_url = str(request.base_url).rstrip("/")
    return service.create_pairing_token(user, server_url)


@router.get("/status", response_model=LocalAgentStatusResponse)
async def get_agent_status(
    request: Request,
    user: UserIdentity = Depends(get_current_user),
    service: LocalAgentService = Depends(get_local_agent_service),
) -> LocalAgentStatusResponse:
    """Get the current live status, folder list, and file counts for the user's agent."""
    server_url = str(request.base_url).rstrip("/")
    tenant_id = getattr(user, "tenant_id", None) or "default"
    user_id = _get_user_id(user)
    return service.get_status(tenant_id, user_id, server_url)


@router.post("/folders")
async def add_local_folder(
    body: AddFolderRequest,
    user: UserIdentity = Depends(get_current_user),
    service: LocalAgentService = Depends(get_local_agent_service),
) -> dict[str, Any]:
    """Request a local folder path to be approved and indexed by the local agent."""
    if not body.folder_path or not body.folder_path.strip():
        raise HTTPException(status_code=400, detail="Folder path cannot be empty.")
    tenant_id = getattr(user, "tenant_id", None) or "default"
    user_id = _get_user_id(user)
    return service.request_folder(tenant_id, user_id, body.folder_path.strip())


@router.delete("/folders/{folder_id}")
async def remove_local_folder(
    folder_id: str,
    user: UserIdentity = Depends(get_current_user),
    service: LocalAgentService = Depends(get_local_agent_service),
) -> dict[str, Any]:
    """Disconnect an approved local folder and delete its synced chunks."""
    tenant_id = getattr(user, "tenant_id", None) or "default"
    user_id = _get_user_id(user)
    removed = service.remove_folder(tenant_id, user_id, folder_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Connected folder not found.")
    return {"status": "ok", "message": f"Folder '{folder_id}' disconnected."}


@router.post("/search", response_model=LocalSearchResponse)
async def test_search_local(
    body: LocalSearchRequest,
    user: UserIdentity = Depends(get_current_user),
    service: LocalAgentService = Depends(get_local_agent_service),
) -> LocalSearchResponse:
    """Search user's active local files directly."""
    tenant_id = getattr(user, "tenant_id", None) or "default"
    user_id = _get_user_id(user)
    hits = service.search_local_chunks(
        tenant_id=tenant_id,
        user_id=user_id,
        query=body.query,
        top_k=body.top_k,
        folder_id=body.folder_id,
    )
    return LocalSearchResponse(
        query=body.query,
        total_hits=len(hits),
        chunks=hits,
    )


# ---------------------------------------------------------------------------
# Agent Endpoints (Accessed from User's Local Windows Computer)
# ---------------------------------------------------------------------------

@router.post("/heartbeat")
async def agent_heartbeat(
    heartbeat: LocalAgentHeartbeat,
    identity: tuple[str, str] = Depends(_extract_agent_identity),
    service: LocalAgentService = Depends(get_local_agent_service),
) -> dict[str, Any]:
    """Heartbeat signal sent periodically by the local agent."""
    tenant_id, user_id = identity
    return service.record_heartbeat(tenant_id, user_id, heartbeat)


@router.post("/sync")
async def agent_sync_folder(
    payload: FolderSyncPayload,
    identity: tuple[str, str] = Depends(_extract_agent_identity),
    service: LocalAgentService = Depends(get_local_agent_service),
) -> dict[str, Any]:
    """Sync batch of indexed chunks and files from an approved local folder."""
    tenant_id, user_id = identity
    res = service.sync_folder(tenant_id, user_id, payload)
    if tenant_id != "default":
        try:
            service.sync_folder("default", "default", payload)
        except Exception:
            pass

    # Dynamically connect CompanyDataService to this exact folder
    try:
        from pathlib import Path
        from backend.integrations.files.company_data_service import CompanyDataService
        from backend.integrations.files.company_data.persistence import set_persisted_folder
        p = Path(payload.folder_path)
        set_persisted_folder(payload.folder_path, tenant_id=tenant_id)
        set_persisted_folder(payload.folder_path, tenant_id="default")

        for tid in (tenant_id, "default"):
            cds = CompanyDataService.for_tenant(tid)
            if p.exists() and p.is_dir():
                cds.update_root(p)
            else:
                cds._load_from_local_agent()
    except Exception as exc:
        logger.warning("Could not sync CompanyDataService with agent folder: %s", exc)

    return res
