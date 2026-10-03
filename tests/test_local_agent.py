"""Unit and integration tests for Nanvi Local File Agent and Cloud API."""
from __future__ import annotations

import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from backend.agents.models import AgentRequest
from backend.local_agent.models import (
    FolderSyncPayload,
    LocalAgentHeartbeat,
    LocalChunkRecord,
    LocalFileRecord,
    LocalFolderInfo,
)
from backend.local_agent.service import LocalAgentService
from backend.local_agent.store import LocalAgentStore
from backend.security.models import UserIdentity
from local_agent.nanvi_local_agent import NanviLocalAgent, SecurityError


@pytest.fixture
def temp_store(tmp_path):
    store_file = tmp_path / "test_local_agent_store.json"
    return LocalAgentStore(persistence_file=store_file)


@pytest.fixture
def local_service(temp_store):
    return LocalAgentService(store=temp_store)


@pytest.fixture
def mock_user():
    from backend.security.authorization.rbac import Role
    return UserIdentity(
        subject="usr-123",
        issuer="nanvi-test",
        tenant_id="tenant-abc",
        name="Test Engineer",
        roles=frozenset({Role.PROJECT_ENGINEER}),
    )


# ---------------------------------------------------------------------------
# 1. Pairing Token Tests
# ---------------------------------------------------------------------------

def test_pairing_token_creation_and_verification(local_service, mock_user):
    token_resp = local_service.create_pairing_token(mock_user, "http://127.0.0.1:8000")
    assert token_resp.token
    assert token_resp.tenant_id == "tenant-abc"
    assert token_resp.user_id == "usr-123"

    payload = local_service.verify_agent_token(token_resp.token)
    assert payload["sub"] == "usr-123"
    assert payload["tenant_id"] == "tenant-abc"
    assert payload["aud"] == "nanvi-local-agent"


def test_tampered_token_rejected(local_service):
    with pytest.raises(Exception):
        local_service.verify_agent_token("invalid.tampered.token")


# ---------------------------------------------------------------------------
# 2. Local Agent Store & Heartbeat Tests
# ---------------------------------------------------------------------------

def test_heartbeat_and_online_status(local_service):
    tenant_id = "tenant-abc"
    user_id = "usr-123"

    # Initially offline
    status = local_service.get_status(tenant_id, user_id)
    assert not status.is_online
    assert status.total_files == 0

    # Send heartbeat
    hb = LocalAgentHeartbeat(
        agent_version="1.0.0",
        folders=[
            LocalFolderInfo(
                folder_id="C:/Projects",
                folder_path="C:/Projects",
                display_name="Projects",
                file_count=12,
                chunk_count=24,
            )
        ],
    )
    local_service.record_heartbeat(tenant_id, user_id, hb)

    # Now online
    status_after = local_service.get_status(tenant_id, user_id)
    assert status_after.is_online
    assert len(status_after.connected_folders) == 1
    assert status_after.connected_folders[0].folder_path == "C:/Projects"


# ---------------------------------------------------------------------------
# 3. Sync & Search Tests
# ---------------------------------------------------------------------------

def test_sync_and_search_chunks(local_service):
    tenant_id = "tenant-abc"
    user_id = "usr-123"

    payload = FolderSyncPayload(
        folder_id="C:/Projects",
        folder_path="C:/Projects",
        display_name="Projects",
        files=[
            LocalFileRecord(
                relative_path="Chennai_Bridge/Inspection_Report.pdf",
                filename="Inspection_Report.pdf",
                folder_name="Projects",
                file_type="pdf",
                size_bytes=1024,
                chunk_count=2,
            )
        ],
        chunks=[
            LocalChunkRecord(
                chunk_id="chunk-001",
                relative_path="Chennai_Bridge/Inspection_Report.pdf",
                filename="Inspection_Report.pdf",
                folder_name="Projects",
                chunk_index=0,
                text="The Chennai River Bridge foundation pile load test exceeded the 4500 kN requirement.",
            ),
            LocalChunkRecord(
                chunk_id="chunk-002",
                relative_path="Cooum_Flyover/Safety_Audit.docx",
                filename="Safety_Audit.docx",
                folder_name="Projects",
                chunk_index=0,
                text="Safety helmets and harnesses are mandatory for all elevated beam workers.",
            ),
        ],
    )

    local_service.sync_folder(tenant_id, user_id, payload)

    # Search for bridge
    hits = local_service.search_local_chunks(tenant_id, user_id, "Chennai Bridge foundation", top_k=5)
    assert len(hits) >= 1
    top = hits[0]
    assert "Inspection_Report.pdf" in top.filename
    assert top.citation == "Projects/Chennai_Bridge/Inspection_Report.pdf"
    assert "4500 kN" in top.text

    # Search for safety
    safety_hits = local_service.search_local_chunks(tenant_id, user_id, "helmets safety", top_k=5)
    assert len(safety_hits) >= 1
    assert "Safety_Audit.docx" in safety_hits[0].filename


def test_remove_folder(local_service):
    tenant_id = "tenant-abc"
    user_id = "usr-123"

    payload = FolderSyncPayload(
        folder_id="C:/TempData",
        folder_path="C:/TempData",
        display_name="TempData",
        chunks=[
            LocalChunkRecord(
                chunk_id="chunk-temp",
                relative_path="file.txt",
                filename="file.txt",
                folder_name="TempData",
                text="Temporary content.",
            )
        ],
    )
    local_service.sync_folder(tenant_id, user_id, payload)

    assert len(local_service.search_local_chunks(tenant_id, user_id, "Temporary")) == 1

    # Remove folder
    removed = local_service.remove_folder(tenant_id, user_id, "C:/TempData")
    assert removed
    assert len(local_service.search_local_chunks(tenant_id, user_id, "Temporary")) == 0


# ---------------------------------------------------------------------------
# 4. Local Agent Client Security & Parsing Tests
# ---------------------------------------------------------------------------

def test_local_agent_security_blocks_system_roots(tmp_path):
    agent = NanviLocalAgent(server_url="http://127.0.0.1:8000", token="dummy-token", config_path=tmp_path / "cfg.json")

    # Reject non-existent
    with pytest.raises(SecurityError, match="does not exist"):
        agent.validate_folder_path("C:/NonExistentPath_XYZ_123")

    # Reject system root (if Windows)
    win_path = Path("C:/Windows")
    if win_path.exists():
        with pytest.raises(SecurityError, match="restricted|prohibited"):
            agent.validate_folder_path(win_path)


def test_local_agent_chunking_and_extraction(tmp_path):
    agent = NanviLocalAgent(server_url="http://127.0.0.1:8000", token="dummy-token", config_path=tmp_path / "cfg.json")

    # Create dummy text file
    sample_dir = tmp_path / "sample_folder"
    sample_dir.mkdir()
    sample_file = sample_dir / "report.txt"
    sample_file.write_text("Nanvi enterprise assistant bridge construction inspection data.", encoding="utf-8")

    text = agent._extract_text(sample_file)
    assert "bridge construction" in text

    chunks = agent.chunk_text(text, "report.txt", "report.txt", "sample_folder", "2026-10-03T00:00:00Z")
    assert len(chunks) == 1
    assert chunks[0]["filename"] == "report.txt"
    assert "bridge construction" in chunks[0]["text"]


# ---------------------------------------------------------------------------
# 5. KnowledgeAgent RAG Integration Test
# ---------------------------------------------------------------------------

def test_knowledge_agent_retrieves_local_chunks(local_service, mock_user, monkeypatch):
    from backend.agents.knowledge_agent import KnowledgeAgent
    from backend.agents.models import Capability

    # Seed local chunk
    payload = FolderSyncPayload(
        folder_id="C:/Engineering",
        folder_path="C:/Engineering",
        display_name="Engineering",
        chunks=[
            LocalChunkRecord(
                chunk_id="chunk-eng-1",
                relative_path="Pylons/Stress_Analysis.csv",
                filename="Stress_Analysis.csv",
                folder_name="Engineering",
                text="The bridge pylon maximum tensile stress is 320 MPa under dynamic wind load.",
            )
        ],
    )
    local_service.sync_folder(mock_user.tenant_id, mock_user.subject, payload)

    # Monkeypatch singleton
    monkeypatch.setattr("backend.local_agent.service._service_instance", local_service)

    agent = KnowledgeAgent(company_data_service=None)
    req = AgentRequest(
        request_id="req-test-1",
        user=mock_user,
        query="What is the pylon maximum tensile stress?",
    )

    resp = agent.run(req)
    assert resp.capability == Capability.KNOWLEDGE
    assert "320 MPa" in str(resp.content)
    assert len(resp.sources) >= 1
    assert "Stress_Analysis.csv" in resp.sources[0].title
