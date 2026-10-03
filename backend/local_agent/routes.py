"""FastAPI router for Nanvi Local File Agent endpoints."""
from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status

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
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or malformed Authorization header. Expected 'Bearer <pairing_token>'",
        )
    token = authorization.split(" ", 1)[1].strip()
    payload = service.verify_agent_token(token)
    tenant_id = payload.get("tenant_id", "default")
    user_id = payload.get("sub", "default")
    return tenant_id, user_id


# ---------------------------------------------------------------------------
# User Endpoints (Accessed from Frontend Web App)
# ---------------------------------------------------------------------------

def _get_user_id(user: UserIdentity) -> str:
    return str(getattr(user, "subject", None) or getattr(user, "user_id", "default"))


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

    server_url = str(request.base_url).rstrip("/")
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
            raise HTTPException(status_code=401, detail="Invalid download token.")
    else:
        raise HTTPException(status_code=401, detail="Authentication required to download agent package.")

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
    return service.sync_folder(tenant_id, user_id, payload)
