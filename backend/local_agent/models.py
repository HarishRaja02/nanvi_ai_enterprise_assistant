"""Pydantic models for Nanvi Local File Agent communication and metadata."""
from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field


class LocalAgentTokenResponse(BaseModel):
    """Pairing token issued to authenticated user for their local agent."""
    token: str
    expires_in_days: int = 30
    server_url: str
    tenant_id: str
    user_id: str
    display_name: str


class LocalFolderInfo(BaseModel):
    """Summary of an approved folder on the user's local machine."""
    folder_id: str
    folder_path: str
    display_name: str
    file_count: int = 0
    chunk_count: int = 0
    status: str = "connected"
    last_synced_at: str | None = None


class LocalAgentStatusResponse(BaseModel):
    """Current live status of the user's Local File Agent."""
    is_online: bool
    last_heartbeat: str | None = None
    agent_version: str | None = None
    connected_folders: list[LocalFolderInfo] = Field(default_factory=list)
    total_files: int = 0
    total_chunks: int = 0
    pairing_command: str = ""


class LocalAgentHeartbeat(BaseModel):
    """Periodic heartbeat sent from local agent to maintain online status."""
    agent_version: str = "1.0.0"
    folders: list[LocalFolderInfo] = Field(default_factory=list)


class AddFolderRequest(BaseModel):
    """Request from user Web UI to add/approve a local folder path."""
    folder_path: str


class LocalChunkRecord(BaseModel):
    """Individual chunk extracted from a local file."""
    chunk_id: str
    relative_path: str
    filename: str
    folder_name: str
    chunk_index: int = 0
    text: str
    char_count: int = 0
    modified_at: str | None = None
    page: int | None = None
    sheet: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class LocalFileRecord(BaseModel):
    """Metadata summary of an indexed file."""
    relative_path: str
    filename: str
    folder_name: str
    file_type: str
    size_bytes: int = 0
    chunk_count: int = 0
    modified_at: str | None = None


class FolderSyncPayload(BaseModel):
    """Batch update of files and chunks from an approved local folder."""
    folder_id: str
    folder_path: str
    display_name: str
    files: list[LocalFileRecord] = Field(default_factory=list)
    chunks: list[LocalChunkRecord] = Field(default_factory=list)


class LocalSearchRequest(BaseModel):
    """Search query routed to local files."""
    query: str
    top_k: int = 5
    folder_id: str | None = None


class LocalSearchChunk(BaseModel):
    """Search hit from local file search with citation details."""
    chunk_id: str
    folder_name: str
    folder_path: str
    relative_path: str
    filename: str
    citation: str
    text: str
    score: float = 0.0
    page: int | None = None
    sheet: str | None = None
    modified_at: str | None = None


class LocalSearchResponse(BaseModel):
    """Result of searching the user's local documents."""
    query: str
    total_hits: int
    chunks: list[LocalSearchChunk]
