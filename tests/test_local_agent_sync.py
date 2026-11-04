"""Tests for local agent batched syncing and requested folders deduplication."""
import pytest
from backend.local_agent.models import FolderSyncPayload, LocalChunkRecord, LocalFileRecord
from backend.local_agent.store import LocalAgentStore


def test_sync_folder_batched_append():
    """Verify that batched uploads with replace_all=True then False correctly accumulate chunks and files."""
    store = LocalAgentStore()
    tenant_id = "test-tenant"
    user_id = "test-user"

    # Batch 1: replace_all=True with files list and first 2 chunks
    files = [
        LocalFileRecord(relative_path="doc1.pdf", filename="doc1.pdf", folder_name="PDF", file_type="pdf", size_bytes=1000, chunk_count=2),
        LocalFileRecord(relative_path="doc2.pdf", filename="doc2.pdf", folder_name="PDF", file_type="pdf", size_bytes=2000, chunk_count=2),
    ]
    chunks_batch1 = [
        LocalChunkRecord(chunk_id="c1", relative_path="doc1.pdf", filename="doc1.pdf", folder_name="PDF", chunk_index=0, text="First chunk"),
        LocalChunkRecord(chunk_id="c2", relative_path="doc1.pdf", filename="doc1.pdf", folder_name="PDF", chunk_index=1, text="Second chunk"),
    ]
    payload1 = FolderSyncPayload(
        folder_id="H:/PDF",
        folder_path="H:/PDF",
        display_name="PDF",
        files=files,
        chunks=chunks_batch1,
        replace_all=True,
    )
    store.sync_folder(tenant_id, user_id, payload1)

    status = store.get_agent_status(tenant_id, user_id)
    assert status["total_files"] == 2
    assert status["total_chunks"] == 2

    # Batch 2: replace_all=False with next 2 chunks and empty files list
    chunks_batch2 = [
        LocalChunkRecord(chunk_id="c3", relative_path="doc2.pdf", filename="doc2.pdf", folder_name="PDF", chunk_index=0, text="Third chunk"),
        LocalChunkRecord(chunk_id="c4", relative_path="doc2.pdf", filename="doc2.pdf", folder_name="PDF", chunk_index=1, text="Fourth chunk"),
    ]
    payload2 = FolderSyncPayload(
        folder_id="H:/PDF",
        folder_path="H:/PDF",
        display_name="PDF",
        files=[],
        chunks=chunks_batch2,
        replace_all=False,
    )
    store.sync_folder(tenant_id, user_id, payload2)

    status2 = store.get_agent_status(tenant_id, user_id)
    assert status2["total_files"] == 2  # Preserved!
    assert status2["total_chunks"] == 4  # Accumulated!


def test_requested_folders_popped_on_heartbeat():
    """Verify requested folders are returned once and popped so they don't loop indefinitely."""
    store = LocalAgentStore()
    tenant_id = "test-tenant"
    user_id = "test-user"

    store.request_folder(tenant_id, user_id, "C:/MyFolder")
    from backend.local_agent.models import LocalAgentHeartbeat
    hb = LocalAgentHeartbeat()

    # First heartbeat: should return the requested folder
    reqs, cmds = store.record_heartbeat_and_pop_commands(tenant_id, user_id, hb)
    assert "C:/MyFolder" in reqs

    # Second heartbeat: should NOT return it again!
    reqs2, cmds2 = store.record_heartbeat_and_pop_commands(tenant_id, user_id, hb)
    assert len(reqs2) == 0

