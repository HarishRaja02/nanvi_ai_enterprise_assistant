"""Per-user persistent storage for Nanvi Local File Agent registrations and chunks."""
from __future__ import annotations

import json
import logging
import math
import re
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import (
    FolderSyncPayload,
    LocalAgentHeartbeat,
    LocalFolderInfo,
    LocalSearchChunk,
)

logger = logging.getLogger(__name__)

STORAGE_FILE = Path(__file__).resolve().parents[2] / "storage" / "local_agent_store.json"
HEARTBEAT_TTL_SECONDS = 35.0  # Agent is considered offline if no heartbeat within 35 seconds


class LocalAgentStore:
    """Thread-safe store for local agent status, approved folders, and synced chunks."""

    def __init__(self, persistence_file: Path | str | None = None) -> None:
        self._path = Path(persistence_file) if persistence_file else STORAGE_FILE
        self._lock = threading.Lock()
        # Structure: {(tenant_id, user_id): {"agent": dict, "folders": dict[folder_id, dict], "chunks": list[dict]}}
        self._data: dict[tuple[str, str], dict[str, Any]] = {}
        self._load()

    def _key(self, tenant_id: str, user_id: str) -> tuple[str, str]:
        return (str(tenant_id or "default").strip(), str(user_id or "default").strip())

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            for entry in raw:
                k = (entry["tenant_id"], entry["user_id"])
                self._data[k] = {
                    "agent": entry.get("agent", {}),
                    "folders": entry.get("folders", {}),
                    "chunks": entry.get("chunks", []),
                }
        except Exception as exc:
            logger.warning("Could not load local_agent_store.json: %s", exc)

    def _save_unlocked(self) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            export = []
            for (tenant_id, user_id), val in self._data.items():
                export.append({
                    "tenant_id": tenant_id,
                    "user_id": user_id,
                    "agent": val.get("agent", {}),
                    "folders": val.get("folders", {}),
                    "chunks": val.get("chunks", []),
                })
            self._path.write_text(json.dumps(export, indent=2), encoding="utf-8")
        except Exception as exc:
            logger.warning("Could not persist local_agent_store.json: %s", exc)

    def record_heartbeat(self, tenant_id: str, user_id: str, heartbeat: LocalAgentHeartbeat) -> None:
        """Update last seen timestamp, agent version, and folder list from local agent."""
        k = self._key(tenant_id, user_id)
        with self._lock:
            if k not in self._data:
                self._data[k] = {"agent": {}, "folders": {}, "chunks": []}

            now_iso = datetime.now(timezone.utc).isoformat()
            self._data[k]["agent"] = {
                "last_heartbeat": now_iso,
                "last_heartbeat_ts": time.time(),
                "agent_version": heartbeat.agent_version,
            }

            # Update folders if provided
            if heartbeat.folders:
                folder_map = self._data[k].setdefault("folders", {})
                for f in heartbeat.folders:
                    fid = f.folder_id or f.folder_path
                    existing = folder_map.get(fid, {})
                    folder_map[fid] = {
                        "folder_id": fid,
                        "folder_path": f.folder_path,
                        "display_name": f.display_name or Path(f.folder_path).name or f.folder_path,
                        "file_count": f.file_count,
                        "chunk_count": existing.get("chunk_count", f.chunk_count),
                        "status": f.status or "connected",
                        "last_synced_at": existing.get("last_synced_at") or now_iso,
                    }
            self._save_unlocked()

    def get_agent_status(self, tenant_id: str, user_id: str) -> dict[str, Any]:
        """Check if local agent is currently online and return its folder summary."""
        k = self._key(tenant_id, user_id)
        with self._lock:
            val = self._data.get(k, {})
            agent = val.get("agent", {})
            last_ts = agent.get("last_heartbeat_ts", 0.0)
            is_online = (time.time() - last_ts) < HEARTBEAT_TTL_SECONDS

            folders = []
            total_files = 0
            total_chunks = len(val.get("chunks", []))

            for f_dict in val.get("folders", {}).values():
                total_files += f_dict.get("file_count", 0)
                folders.append(LocalFolderInfo(**f_dict))

            return {
                "is_online": is_online,
                "last_heartbeat": agent.get("last_heartbeat"),
                "agent_version": agent.get("agent_version"),
                "connected_folders": folders,
                "total_files": total_files,
                "total_chunks": total_chunks,
            }

    def sync_folder(self, tenant_id: str, user_id: str, payload: FolderSyncPayload) -> None:
        """Store or replace indexed chunks for an approved folder."""
        k = self._key(tenant_id, user_id)
        with self._lock:
            if k not in self._data:
                self._data[k] = {"agent": {}, "folders": {}, "chunks": []}

            fid = payload.folder_id or payload.folder_path
            now_iso = datetime.now(timezone.utc).isoformat()

            # 1. Update folder registry
            folders = self._data[k].setdefault("folders", {})
            folders[fid] = {
                "folder_id": fid,
                "folder_path": payload.folder_path,
                "display_name": payload.display_name or Path(payload.folder_path).name or fid,
                "file_count": len(payload.files) if payload.files else len({c.relative_path for c in payload.chunks}),
                "chunk_count": len(payload.chunks),
                "status": "synced",
                "last_synced_at": now_iso,
            }

            # 2. Replace chunks belonging to this folder
            existing_chunks = self._data[k].get("chunks", [])
            retained_chunks = [c for c in existing_chunks if c.get("folder_id") != fid]

            for c in payload.chunks:
                retained_chunks.append({
                    "chunk_id": c.chunk_id,
                    "folder_id": fid,
                    "folder_path": payload.folder_path,
                    "folder_name": c.folder_name or payload.display_name or Path(payload.folder_path).name,
                    "relative_path": c.relative_path,
                    "filename": c.filename,
                    "chunk_index": c.chunk_index,
                    "text": c.text,
                    "modified_at": c.modified_at or now_iso,
                    "page": c.page,
                    "sheet": c.sheet,
                    "metadata": c.metadata,
                })

            self._data[k]["chunks"] = retained_chunks
            self._save_unlocked()
            logger.info("Synced %d chunks for local folder '%s' (user %s)", len(payload.chunks), fid, user_id)

    def remove_folder(self, tenant_id: str, user_id: str, folder_id: str) -> bool:
        """Remove a connected folder and its chunks."""
        k = self._key(tenant_id, user_id)
        with self._lock:
            val = self._data.get(k)
            if not val:
                return False
            folders = val.get("folders", {})
            if folder_id in folders:
                del folders[folder_id]
                # Also remove chunks
                val["chunks"] = [c for c in val.get("chunks", []) if c.get("folder_id") != folder_id]
                self._save_unlocked()
                return True
            # Check by folder_path
            for fid, f in list(folders.items()):
                if f.get("folder_path") == folder_id:
                    del folders[fid]
                    val["chunks"] = [c for c in val.get("chunks", []) if c.get("folder_id") != fid]
                    self._save_unlocked()
                    return True
            return False

    def search_chunks(
        self,
        tenant_id: str,
        user_id: str,
        query: str,
        top_k: int = 5,
        folder_id: str | None = None,
    ) -> list[LocalSearchChunk]:
        """Perform fast keyword and relevance search over user's local chunks."""
        k = self._key(tenant_id, user_id)
        with self._lock:
            val = self._data.get(k, {})
            chunks = val.get("chunks", [])
            if not chunks:
                return []

        q_terms = set(re.findall(r"\w+", query.casefold()))
        if not q_terms:
            return []

        results: list[tuple[float, dict[str, Any]]] = []

        for c in chunks:
            if folder_id and c.get("folder_id") != folder_id:
                continue

            text = c.get("text", "")
            text_cf = text.casefold()
            fn_cf = c.get("filename", "").casefold()
            rel_cf = c.get("relative_path", "").casefold()

            score = 0.0

            # Exact phrase match
            if query.casefold() in text_cf:
                score += 5.0
            if query.casefold() in fn_cf:
                score += 10.0

            # Term overlap
            text_tokens = re.findall(r"\w+", text_cf)
            fn_tokens = re.findall(r"\w+", fn_cf)
            rel_tokens = re.findall(r"\w+", rel_cf)

            matched_terms = 0
            for term in q_terms:
                t_count = text_tokens.count(term)
                if t_count > 0:
                    matched_terms += 1
                    # Log-frequency term score
                    score += 1.0 + math.log(1.0 + t_count)
                if term in fn_tokens:
                    score += 3.0
                if term in rel_tokens:
                    score += 2.0

            # Coverage boost
            if len(q_terms) > 1 and matched_terms == len(q_terms):
                score *= 1.5

            if score > 0.5:
                results.append((score, c))

        results.sort(key=lambda x: x[0], reverse=True)
        top = results[:top_k]

        hits: list[LocalSearchChunk] = []
        for s, c in top:
            folder_name = c.get("folder_name", "")
            rel_path = c.get("relative_path", "")
            citation = f"{folder_name}/{rel_path}" if folder_name else rel_path
            hits.append(LocalSearchChunk(
                chunk_id=c.get("chunk_id", ""),
                folder_name=folder_name,
                folder_path=c.get("folder_path", ""),
                relative_path=rel_path,
                filename=c.get("filename", ""),
                citation=citation,
                text=c.get("text", ""),
                score=round(s, 3),
                page=c.get("page"),
                sheet=c.get("sheet"),
                modified_at=c.get("modified_at"),
            ))
        return hits
