"""Per-user persistent storage for Nanvi Local File Agent registrations and chunks."""
from __future__ import annotations

import json
import logging
import math
import os
import re
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.core.config import settings
from .models import (
    FolderSyncPayload,
    LocalAgentHeartbeat,
    LocalFolderInfo,
    LocalSearchChunk,
)

logger = logging.getLogger(__name__)

HEARTBEAT_TTL_SECONDS = 45.0  # Agent is considered offline if no heartbeat within 45 seconds


def _default_storage_file() -> Path:
    """Determine a writable local path for file fallback storage."""
    if os.getenv("VERCEL") or not os.access(Path(__file__).resolve().parents[2], os.W_OK):
        return Path(tempfile.gettempdir()) / "nanvi_local_agent_store.json"
    p = Path(__file__).resolve().parents[2] / "storage" / "local_agent_store.json"
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        return p
    except Exception:
        return Path(tempfile.gettempdir()) / "nanvi_local_agent_store.json"


class LocalAgentStore:
    """Thread-safe store for local agent status, approved folders, and synced chunks.

    Supports PostgreSQL / Supabase storage (essential on serverless Vercel) with
    automatic fallback to local JSON file.
    """

    def __init__(self, dsn: str = "", persistence_file: Path | str | None = None) -> None:
        self._path = Path(persistence_file) if persistence_file else _default_storage_file()
        self._lock = threading.Lock()
        self._dsn = dsn
        if not self._dsn and persistence_file is None:
            # Use Supabase/PostgreSQL if available
            self._dsn = settings.supabase_database_url or settings.database_url or ""
            # Don't use localhost DB in production
            if settings.is_production and ("localhost" in self._dsn or "127.0.0.1" in self._dsn):
                self._dsn = ""

        # In-memory fast cache: {(tenant_id, user_id): dict}
        self._data: dict[tuple[str, str], dict[str, Any]] = {}
        self._load_local_file()
        if self._dsn:
            self._init_db()

    def _key(self, tenant_id: str, user_id: str) -> tuple[str, str]:
        return (str(tenant_id or "default").strip(), str(user_id or "default").strip())

    def _init_db(self) -> None:
        """Create PostgreSQL table if it doesn't already exist."""
        if not self._dsn:
            return
        try:
            import psycopg
            with psycopg.connect(self._dsn, autocommit=True, connect_timeout=4) as conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS public.nanvi_local_agent_store (
                        tenant_id TEXT NOT NULL,
                        user_id TEXT NOT NULL,
                        data JSONB NOT NULL,
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        PRIMARY KEY (tenant_id, user_id)
                    );
                    """
                )
        except Exception as exc:
            logger.warning("Could not initialize PostgreSQL local agent table (%s). Using local storage.", exc)
            self._dsn = ""

    def _load_local_file(self) -> None:
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
                    "requested_folders": entry.get("requested_folders", []),
                }
        except Exception as exc:
            logger.debug("Could not load local_agent_store.json: %s", exc)

    def _save_local_file_unlocked(self) -> None:
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
                    "requested_folders": val.get("requested_folders", []),
                })
            self._path.write_text(json.dumps(export, indent=2), encoding="utf-8")
        except Exception as exc:
            logger.debug("Could not persist local_agent_store.json: %s", exc)

    def _load_key(self, tenant_id: str, user_id: str) -> dict[str, Any]:
        """Fetch fresh state for a tenant/user from PostgreSQL or memory."""
        k = self._key(tenant_id, user_id)
        if self._dsn:
            try:
                import psycopg
                from psycopg.rows import dict_row
                with psycopg.connect(self._dsn, autocommit=True, connect_timeout=3, row_factory=dict_row) as conn:
                    row = conn.execute(
                        "SELECT data FROM public.nanvi_local_agent_store WHERE tenant_id = %s AND user_id = %s",
                        (k[0], k[1]),
                    ).fetchone()
                    if row and row.get("data"):
                        d = row["data"]
                        self._data[k] = {
                            "agent": d.get("agent", {}),
                            "folders": d.get("folders", {}),
                            "chunks": d.get("chunks", []),
                            "requested_folders": d.get("requested_folders", []),
                        }
                        return self._data[k]
            except Exception as exc:
                logger.debug("PostgreSQL load error for %s: %s", k, exc)

        return self._data.setdefault(k, {"agent": {}, "folders": {}, "chunks": [], "requested_folders": []})

    def _save_key(self, tenant_id: str, user_id: str, val: dict[str, Any]) -> None:
        """Persist state for a tenant/user to PostgreSQL and local file."""
        k = self._key(tenant_id, user_id)
        self._data[k] = val
        if self._dsn:
            try:
                import psycopg
                with psycopg.connect(self._dsn, autocommit=True, connect_timeout=3) as conn:
                    conn.execute(
                        """
                        INSERT INTO public.nanvi_local_agent_store (tenant_id, user_id, data, updated_at)
                        VALUES (%s, %s, %s::jsonb, NOW())
                        ON CONFLICT (tenant_id, user_id)
                        DO UPDATE SET data = EXCLUDED.data, updated_at = NOW()
                        """,
                        (k[0], k[1], json.dumps(val)),
                    )
                return
            except Exception as exc:
                logger.warning("PostgreSQL save error for %s: %s", k, exc)

        self._save_local_file_unlocked()

    def record_heartbeat(self, tenant_id: str, user_id: str, heartbeat: LocalAgentHeartbeat) -> None:
        """Update last seen timestamp, agent version, and folder list from local agent."""
        k = self._key(tenant_id, user_id)
        with self._lock:
            val = self._load_key(tenant_id, user_id)
            now_iso = datetime.now(timezone.utc).isoformat()
            val["agent"] = {
                "last_heartbeat": now_iso,
                "last_heartbeat_ts": time.time(),
                "agent_version": heartbeat.agent_version,
            }

            # Update folders if provided
            if heartbeat.folders:
                folder_map = val.setdefault("folders", {})
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
            self._save_key(tenant_id, user_id, val)

    def request_folder(self, tenant_id: str, user_id: str, folder_path: str) -> None:
        """User from Web UI requested a folder to be indexed by their local agent."""
        k = self._key(tenant_id, user_id)
        with self._lock:
            val = self._load_key(tenant_id, user_id)
            reqs = val.setdefault("requested_folders", [])
            clean_path = str(folder_path).strip()
            if clean_path and clean_path not in reqs:
                reqs.append(clean_path)
            self._save_key(tenant_id, user_id, val)

    def get_requested_folders(self, tenant_id: str, user_id: str) -> list[str]:
        """Get list of folder paths requested by user via Web UI."""
        with self._lock:
            val = self._load_key(tenant_id, user_id)
            return list(val.get("requested_folders", []))

    def get_agent_status(self, tenant_id: str, user_id: str) -> dict[str, Any]:
        """Check if local agent is currently online and return its folder summary."""
        with self._lock:
            val = self._load_key(tenant_id, user_id)
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
            val = self._load_key(tenant_id, user_id)
            fid = payload.folder_id or payload.folder_path
            now_iso = datetime.now(timezone.utc).isoformat()

            # 1. Update folder registry
            folders = val.setdefault("folders", {})
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
            existing_chunks = val.get("chunks", [])
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

            val["chunks"] = retained_chunks
            self._save_key(tenant_id, user_id, val)
            logger.info("Synced %d chunks for local folder '%s' (user %s)", len(payload.chunks), fid, user_id)

    def remove_folder(self, tenant_id: str, user_id: str, folder_id: str) -> bool:
        """Remove a connected folder and its chunks."""
        with self._lock:
            val = self._load_key(tenant_id, user_id)
            matched = False
            folders = val.get("folders", {})
            folder_path = ""
            if folder_id in folders:
                folder_path = folders[folder_id].get("folder_path", "")
                del folders[folder_id]
                val["chunks"] = [c for c in val.get("chunks", []) if c.get("folder_id") != folder_id]
                matched = True
            else:
                for fid, f in list(folders.items()):
                    if f.get("folder_path") == folder_id:
                        folder_path = f.get("folder_path", "")
                        del folders[fid]
                        val["chunks"] = [c for c in val.get("chunks", []) if c.get("folder_id") != fid]
                        matched = True
                        break

            if matched:
                reqs = val.get("requested_folders", [])
                val["requested_folders"] = [r for r in reqs if r != folder_id and r != folder_path]
                self._save_key(tenant_id, user_id, val)
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
        with self._lock:
            val = self._load_key(tenant_id, user_id)
            chunks = val.get("chunks", [])
            if not chunks:
                return []

            query_terms = [t.lower() for t in re.findall(r"\w+", query) if len(t) > 1]
            if not query_terms:
                return []

            scored: list[tuple[float, dict[str, Any]]] = []
            for c in chunks:
                if folder_id and c.get("folder_id") != folder_id:
                    continue

                text_lower = c.get("text", "").lower()
                rel_path_lower = c.get("relative_path", "").lower()

                score = 0.0
                matched_terms = 0

                for term in query_terms:
                    count_text = text_lower.count(term)
                    count_path = rel_path_lower.count(term)

                    if count_text > 0 or count_path > 0:
                        matched_terms += 1
                        score += (count_text * 1.0) + (count_path * 5.0)

                if matched_terms > 0:
                    coverage = matched_terms / len(query_terms)
                    final_score = score * (1.0 + coverage)
                    scored.append((final_score, c))

            scored.sort(key=lambda x: x[0], reverse=True)

            results: list[LocalSearchChunk] = []
            for score, c in scored[:top_k]:
                rel = c.get("relative_path", "")
                fname = c.get("filename", Path(rel).name)
                f_name = c.get("folder_name", "")
                citation = f"{f_name}/{rel}".strip("/")

                results.append(
                    LocalSearchChunk(
                        chunk_id=c["chunk_id"],
                        folder_name=f_name,
                        folder_path=c.get("folder_path", ""),
                        relative_path=rel,
                        filename=fname,
                        citation=citation,
                        text=c.get("text", ""),
                        score=round(score, 3),
                        page=c.get("page"),
                        sheet=c.get("sheet"),
                        modified_at=c.get("modified_at"),
                    )
                )

            return results
