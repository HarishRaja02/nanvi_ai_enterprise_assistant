"""FastAPI router for Nanvi Local File Agent endpoints."""
from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status

from backend.security.dependencies import get_current_user
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
    return service.get_status(user.tenant_id, user.user_id, server_url)


@router.post("/folders")
async def add_local_folder(
    body: AddFolderRequest,
    user: UserIdentity = Depends(get_current_user),
    service: LocalAgentService = Depends(get_local_agent_service),
) -> dict[str, Any]:
    """Request a local folder path to be approved and indexed by the local agent."""
    if not body.folder_path or not body.folder_path.strip():
        raise HTTPException(status_code=400, detail="Folder path cannot be empty.")
    return service.request_folder(user.tenant_id, user.user_id, body.folder_path.strip())


@router.delete("/folders/{folder_id}")
async def remove_local_folder(
    folder_id: str,
    user: UserIdentity = Depends(get_current_user),
    service: LocalAgentService = Depends(get_local_agent_service),
) -> dict[str, Any]:
    """Disconnect an approved local folder and delete its synced chunks."""
    removed = service.remove_folder(user.tenant_id, user.user_id, folder_id)
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
    hits = service.search_local_chunks(
        tenant_id=user.tenant_id,
        user_id=user.user_id,
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
