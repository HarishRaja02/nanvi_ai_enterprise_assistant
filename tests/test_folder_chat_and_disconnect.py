from pathlib import Path
from unittest.mock import MagicMock
import pytest

from backend.agents.interfaces import AgentRequest
from backend.agents.knowledge_agent import KnowledgeAgent
from backend.local_agent.service import LocalAgentService, get_local_agent_service
from backend.local_agent.models import FolderSyncPayload, LocalChunkRecord, LocalAgentHeartbeat, LocalFolderInfo
from backend.local_agent.store import LocalAgentStore
from backend.security.authorization import UserAttributes


def test_knowledge_agent_answers_from_local_folder_files(tmp_path):
    store = LocalAgentStore(persistence_file=tmp_path / "store.json")
    service = LocalAgentService(store=store)

    import backend.local_agent.service as svc_mod
    orig_svc = svc_mod._service_instance
    svc_mod._service_instance = service

    try:
        tenant_id = "tenant-test"
        user_id = "usr-456"
        user = UserAttributes(user_id=user_id, tenant_id=tenant_id, department="Projects", roles=frozenset({"Employee"}))

        # 1. Sync chunks from a local folder
        payload = FolderSyncPayload(
            folder_id="C:/Users/haris/Documents",
            folder_path="C:/Users/haris/Documents",
            display_name="Documents",
            chunks=[
                LocalChunkRecord(
                    chunk_id="chunk-roadmap-1",
                    relative_path="project_roadmap.pdf",
                    filename="project_roadmap.pdf",
                    folder_name="Documents",
                    text="Project Roadmap 2026: Launching Nanvi AI Assistant across all enterprise divisions by Q3.",
                ),
                LocalChunkRecord(
                    chunk_id="chunk-budget-1",
                    relative_path="q4_budget.xlsx",
                    filename="q4_budget.xlsx",
                    folder_name="Documents",
                    text="Q4 Budget Summary: Total allocated marketing budget is $150,000.",
                ),
            ],
        )
        service.sync_folder(tenant_id, user_id, payload)

        # Setup KnowledgeAgent
        knowledge_agent = KnowledgeAgent(
            company_data_service=None,  # Emulate Vercel cloud environment where CompanyData is remote/empty
        )

        # Query 1: "what files are in my folder?"
        req_listing = AgentRequest(request_id="req-1", user=user, query="what files are in my folder?")
        resp_listing = knowledge_agent.run(req_listing)

        assert resp_listing is not None
        assert "project_roadmap.pdf" in resp_listing.content
        assert "q4_budget.xlsx" in resp_listing.content
        assert len(resp_listing.sources) >= 1

        # Query 2: "summarize the documents in my folder"
        req_summary = AgentRequest(request_id="req-2", user=user, query="summarize the documents in my folder")
        resp_summary = knowledge_agent.run(req_summary)

        assert resp_summary is not None
        assert ("Project Roadmap" in resp_summary.content) or ("Q4 Budget" in resp_summary.content)
        assert len(resp_summary.sources) >= 1

        # Query 3: Specific content inquiry: "what is the marketing budget?"
        req_specific = AgentRequest(request_id="req-3", user=user, query="what is the marketing budget in my files?")
        resp_specific = knowledge_agent.run(req_specific)

        assert resp_specific is not None
        assert "150,000" in resp_specific.content or "budget" in resp_summary.content.lower()
    finally:
        svc_mod._service_instance = orig_svc


def test_folder_disconnect_queues_command_and_prevents_resurrection(tmp_path):
    store = LocalAgentStore(persistence_file=tmp_path / "store2.json")
    service = LocalAgentService(store=store)

    tenant_id = "tenant-test"
    user_id = "usr-456"

    # 1. Sync folder
    folder_path = "C:/Users/haris/Documents"
    payload = FolderSyncPayload(
        folder_id=folder_path,
        folder_path=folder_path,
        display_name="Documents",
        chunks=[
            LocalChunkRecord(
                chunk_id="chunk-1",
                relative_path="file.txt",
                filename="file.txt",
                folder_name="Documents",
                text="Important notes.",
            )
        ],
    )
    service.sync_folder(tenant_id, user_id, payload)

    # Verify online status and folder present
    status_before = service.get_status(tenant_id, user_id)
    assert len(status_before.connected_folders) == 1
    assert status_before.connected_folders[0].folder_id == folder_path

    # 2. Disconnect/remove folder via service
    removed = service.remove_folder(tenant_id, user_id, folder_path)
    assert removed is True

    # Verify folder and chunks removed from store
    status_after = service.get_status(tenant_id, user_id)
    assert len(status_after.connected_folders) == 0
    assert len(service.search_local_chunks(tenant_id, user_id, "Important")) == 0

    # 3. Simulate heartbeat from agent
    # Heartbeat still includes old folder before it receives the remove command
    hb = LocalAgentHeartbeat(
        agent_version="1.0.0",
        folders=[
            LocalFolderInfo(
                folder_id=folder_path,
                folder_path=folder_path,
                display_name="Documents",
                file_count=1,
                chunk_count=1,
                status="connected",
            )
        ],
    )
    hb_resp = service.record_heartbeat(tenant_id, user_id, hb)
    cmds = hb_resp.get("commands", [])

    # Heartbeat popped the queued remove_folder command!
    remove_cmds = [c for c in cmds if c.get("command") == "remove_folder"]
    assert len(remove_cmds) >= 1
    assert remove_cmds[0]["payload"]["folder_path"] == folder_path

    # Crucial: The heartbeat must NOT have resurrected the disconnected folder!
    status_after_hb = service.get_status(tenant_id, user_id)
    assert len(status_after_hb.connected_folders) == 0
