"""Local Agent Service: Token issuance, verification, heartbeat, sync and search coordination."""
from __future__ import annotations

import logging
import time
from typing import Any

import jwt
from fastapi import HTTPException, status

from backend.core.config import settings
from backend.security.models import UserIdentity
from .models import (
    FolderSyncPayload,
    LocalAgentHeartbeat,
    LocalAgentStatusResponse,
    LocalAgentTokenResponse,
    LocalSearchChunk,
)
from .store import LocalAgentStore

logger = logging.getLogger(__name__)

_store: LocalAgentStore | None = None


def get_local_agent_store() -> LocalAgentStore:
    global _store
    if _store is None:
        _store = LocalAgentStore()
    return _store


def sanitize_folder_path(raw_path: str) -> str:
    """Sanitize and clean user-entered folder paths, stripping quotes and accidental CLI prefixes."""
    if not raw_path:
        return ""
    cleaned = str(raw_path).strip().strip("'\"“”`")
    for prefix in [
        "nanvi-agent add",
        "nanvi local agent add",
        "nanvi add",
        "python nanvi_local_agent.py add",
        "python nanvi_gui_agent.py add",
        "python local_agent.py add",
        "python add",
        "add folder",
        "add path",
        "add:",
        "add",
    ]:
        if cleaned.lower().startswith(prefix.lower() + " ") or cleaned.lower() == prefix.lower():
            cleaned = cleaned[len(prefix):].strip().strip("'\"“”`")
            break
    cleaned = cleaned.strip("'\"“”`:").strip()
    return cleaned


class LocalAgentService:
    """Manages pairing tokens and local agent data access."""

    def __init__(self, store: LocalAgentStore | None = None) -> None:
        self.store = store or get_local_agent_store()

    def create_pairing_token(self, user: UserIdentity, server_url: str = "") -> LocalAgentTokenResponse:
        """Issue a 30-day cryptographically signed pairing token bound to the authenticated user."""
        if not settings.jwt_secret:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Local Agent pairing requires JWT_SECRET to be configured.",
            )

        now = int(time.time())
        expires_in = 30 * 24 * 3600  # 30 days
        user_id = getattr(user, "user_id", None) or getattr(user, "subject", "user")
        display_name = getattr(user, "display_name", None) or getattr(user, "name", None) or user.subject
        roles = [r.value if hasattr(r, "value") else str(r) for r in user.roles]
        payload = {
            "sub": user_id,
            "tenant_id": user.tenant_id or "default",
            "display_name": display_name,
            "roles": roles,
            "aud": "nanvi-local-agent",
            "iss": "nanvi-cloud",
            "iat": now,
            "exp": now + expires_in,
        }
        token = jwt.encode(payload, settings.jwt_secret, algorithm="HS256")
        clean_url = server_url.rstrip("/") if server_url else "http://127.0.0.1:8000"

        return LocalAgentTokenResponse(
            token=token,
            expires_in_days=30,
            server_url=clean_url,
            tenant_id=user.tenant_id or "default",
            user_id=user_id,
            display_name=display_name,
        )

    def verify_agent_token(self, token: str) -> dict[str, Any]:
        """Verify the agent's bearer token and return its identity payload."""
        if not settings.jwt_secret:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Local Agent authentication requires JWT_SECRET.",
            )
        try:
            payload = jwt.decode(
                token,
                settings.jwt_secret,
                algorithms=["HS256"],
                audience="nanvi-local-agent",
            )
            return payload
        except jwt.ExpiredSignatureError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Pairing token has expired. Please generate a new pairing token in Settings.",
            )
        except jwt.InvalidTokenError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Invalid pairing token: {exc}",
            )

    def record_heartbeat(self, tenant_id: str, user_id: str, heartbeat: LocalAgentHeartbeat) -> dict[str, Any]:
        """Record heartbeat and return requested folder paths from Web UI."""
        self.store.record_heartbeat(tenant_id, user_id, heartbeat)
        requested_folders = self.store.get_requested_folders(tenant_id, user_id)
        return {
            "status": "ok",
            "message": "Heartbeat recorded",
            "requested_folders": requested_folders,
        }
    def request_folder(self, tenant_id: str, user_id: str, folder_path: str) -> dict[str, Any]:
        """User from Web UI requested a folder to be indexed by their local agent."""
        cleaned = sanitize_folder_path(folder_path)
        if not cleaned:
            raise HTTPException(status_code=400, detail="Please provide a valid folder path.")
        self.store.request_folder(tenant_id, user_id, cleaned)
        return {"status": "ok", "message": f"✓ Folder '{cleaned}' added for indexing."}

    def sync_folder(self, tenant_id: str, user_id: str, payload: FolderSyncPayload) -> dict[str, Any]:
        """Store synced chunks from an authorized local folder."""
        self.store.sync_folder(tenant_id, user_id, payload)
        return {
            "status": "ok",
            "folder_id": payload.folder_id,
            "chunks_synced": len(payload.chunks),
            "files_synced": len(payload.files),
        }

    def remove_folder(self, tenant_id: str, user_id: str, folder_id: str) -> bool:
        """Remove an approved folder from the user's connected folders."""
        return self.store.remove_folder(tenant_id, user_id, folder_id)

    def get_status(self, tenant_id: str, user_id: str, server_url: str = "") -> LocalAgentStatusResponse:
        """Get live online status and folder counts for this user."""
        raw = self.store.get_agent_status(tenant_id, user_id)
        cmd = f"python nanvi_local_agent.py --server {server_url or 'http://127.0.0.1:8000'}"
        return LocalAgentStatusResponse(
            is_online=raw["is_online"],
            last_heartbeat=raw["last_heartbeat"],
            agent_version=raw["agent_version"],
            connected_folders=raw["connected_folders"],
            total_files=raw["total_files"],
            total_chunks=raw["total_chunks"],
            pairing_command=cmd,
        )

    def search_local_chunks(
        self,
        tenant_id: str,
        user_id: str,
        query: str,
        top_k: int = 5,
        folder_id: str | None = None,
    ) -> list[LocalSearchChunk]:
        """Search across user's approved and synced local documents."""
        return self.store.search_chunks(
            tenant_id=tenant_id,
            user_id=user_id,
            query=query,
            top_k=top_k,
            folder_id=folder_id,
        )


_service_instance: LocalAgentService | None = None


def get_local_agent_service() -> LocalAgentService:
    global _service_instance
    if _service_instance is None:
        _service_instance = LocalAgentService()
    return _service_instance
