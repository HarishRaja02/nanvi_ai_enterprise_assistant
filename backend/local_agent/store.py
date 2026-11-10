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
import sys
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
        self._cache_ts: dict[tuple[str, str], float] = {}
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
                    "pending_commands": entry.get("pending_commands", []),
                    "disconnected_folders": entry.get("disconnected_folders", []),
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
                    "pending_commands": val.get("pending_commands", []),
                })
            self._path.write_text(json.dumps(export, indent=2), encoding="utf-8")
        except Exception as exc:
            logger.debug("Could not persist local_agent_store.json: %s", exc)

    def _load_key(self, tenant_id: str, user_id: str) -> dict[str, Any]:
        """Fetch fresh state for a tenant/user from PostgreSQL or memory."""
        k = self._key(tenant_id, user_id)
        now_ts = time.time()
        if k in self._data and (now_ts - self._cache_ts.get(k, 0.0) < 3.0):
            return self._data[k]

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
                            "pending_commands": d.get("pending_commands", []),
                            "disconnected_folders": d.get("disconnected_folders", []),
                        }
                        self._cache_ts[k] = now_ts
                        return self._data[k]

                    # Tenant fallback: find most recent agent data for this tenant
                    tenant_row = conn.execute(
                        "SELECT data FROM public.nanvi_local_agent_store WHERE tenant_id = %s ORDER BY updated_at DESC LIMIT 1",
                        (k[0],),
                    ).fetchone()
                    if tenant_row and tenant_row.get("data"):
                        d = tenant_row["data"]
                        self._data[k] = {
                            "agent": d.get("agent", {}),
                            "folders": d.get("folders", {}),
                            "chunks": d.get("chunks", []),
                            "requested_folders": d.get("requested_folders", []),
                            "pending_commands": d.get("pending_commands", []),
                            "disconnected_folders": d.get("disconnected_folders", []),
                        }
                        self._cache_ts[k] = now_ts
                        return self._data[k]

                    # Global demo fallback: if tenant doesn't match, return most recently updated agent row
                    any_row = conn.execute(
                        "SELECT data FROM public.nanvi_local_agent_store ORDER BY updated_at DESC LIMIT 1"
                    ).fetchone()
                    if any_row and any_row.get("data"):
                        d = any_row["data"]
                        self._data[k] = {
                            "agent": d.get("agent", {}),
                            "folders": d.get("folders", {}),
                            "chunks": d.get("chunks", []),
                            "requested_folders": d.get("requested_folders", []),
                            "pending_commands": d.get("pending_commands", []),
                            "disconnected_folders": d.get("disconnected_folders", []),
                        }
                        self._cache_ts[k] = now_ts
                        return self._data[k]
            except Exception as exc:
                logger.debug("PostgreSQL load error for %s: %s", k, exc)

        # In-memory / file fallback: exact match, then tenant match, then any non-empty match
        if k in self._data and (self._data[k].get("chunks") or self._data[k].get("folders")):
            return self._data[k]
        for (t, u), d in self._data.items():
            if t == k[0] and (d.get("chunks") or d.get("folders")):
                return d
        for (t, u), d in self._data.items():
            if d.get("chunks") or d.get("folders"):
                return d

        return self._data.setdefault(k, {"agent": {}, "folders": {}, "chunks": [], "requested_folders": [], "pending_commands": []})

    def _save_key(self, tenant_id: str, user_id: str, val: dict[str, Any]) -> None:
        """Persist state for a tenant/user to PostgreSQL and local file."""
        k = self._key(tenant_id, user_id)
        self._data[k] = val
        self._cache_ts[k] = time.time()
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
        self.record_heartbeat_and_pop_commands(tenant_id, user_id, heartbeat)

    def record_heartbeat_and_pop_commands(
        self, tenant_id: str, user_id: str, heartbeat: LocalAgentHeartbeat
    ) -> tuple[list[str], list[dict[str, Any]]]:
        """Atomically record heartbeat and pop pending commands in a single fast query."""
        k = self._key(tenant_id, user_id)
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._lock:
            val = self._load_key(tenant_id, user_id)
            val["agent"] = {
                "last_heartbeat": now_iso,
                "last_heartbeat_ts": time.time(),
                "agent_version": heartbeat.agent_version,
            }

            # Update folders if provided (skipping any folders disconnected via Web UI)
            if heartbeat.folders:
                folder_map = val.setdefault("folders", {})
                disconn = set(val.get("disconnected_folders", []))
                for f in heartbeat.folders:
                    fid = f.folder_id or f.folder_path
                    norm_fid = str(fid).replace("\\", "/").rstrip("/").lower()
                    norm_fpath = str(f.folder_path).replace("\\", "/").rstrip("/").lower()
                    if norm_fid in disconn or norm_fpath in disconn:
                        continue
                    existing = folder_map.get(fid, {})
                    file_cnt = f.file_count if f.file_count > 0 else existing.get("file_count", 0)
                    chunk_cnt = f.chunk_count if f.chunk_count > 0 else existing.get("chunk_count", 0)
                    folder_map[fid] = {
                        "folder_id": fid,
                        "folder_path": f.folder_path,
                        "display_name": f.display_name or Path(f.folder_path).name or f.folder_path,
                        "file_count": file_cnt,
                        "chunk_count": chunk_cnt,
                        "status": f.status or "connected",
                        "last_synced_at": existing.get("last_synced_at") or now_iso,
                    }

            # Pop pending commands for this user/agent
            cmds = list(val.get("pending_commands", []))
            val["pending_commands"] = []

            # If polling as a specific user, also grab any pending commands queued to 'default'
            if user_id != "default":
                try:
                    def_val = self._load_key(tenant_id, "default")
                    def_cmds = list(def_val.get("pending_commands", []))
                    if def_cmds:
                        cmds.extend(def_cmds)
                        def_val["pending_commands"] = []
                        self._save_key(tenant_id, "default", def_val)
                except Exception as exc:
                    logger.debug("Could not pop default commands: %s", exc)

            requested_folders = list(val.get("requested_folders", []))
            if requested_folders:
                val["requested_folders"] = []
            if tenant_id != "default":
                try:
                    def_val = self._load_key(tenant_id, "default")
                    def_reqs = list(def_val.get("requested_folders", []))
                    if def_reqs:
                        for dr in def_reqs:
                            if dr not in requested_folders:
                                requested_folders.append(dr)
                        def_val["requested_folders"] = []
                        self._save_key(tenant_id, "default", def_val)
                except Exception:
                    pass

            self._save_key(tenant_id, user_id, val)
            return requested_folders, cmds

    def clear_disconnected(self, folder_path: str) -> None:
        """Clear a folder path and any matching ancestor or descendant from disconnected_folders across all tenants."""
        norm = str(folder_path).replace("\\", "/").rstrip("/").lower()
        base = norm.split("/")[-1] if "/" in norm else norm
        with self._lock:
            for k, val in list(self._data.items()):
                disconn = val.get("disconnected_folders", [])
                if not disconn:
                    continue
                new_disconn = [
                    d for d in disconn
                    if d != norm and d != base and not norm.startswith(d + "/") and not d.startswith(norm + "/")
                ]
                if len(new_disconn) != len(disconn):
                    val["disconnected_folders"] = new_disconn
                    self._save_key(k[0], k[1], val)

    def request_folder(self, tenant_id: str, user_id: str, folder_path: str) -> None:
        """User from Web UI requested a folder to be indexed by their local agent."""
        k = self._key(tenant_id, user_id)
        clean_path = str(folder_path).strip()
        norm_path = clean_path.replace("\\", "/").rstrip("/").lower()
        self.clear_disconnected(clean_path)
        with self._lock:
            val = self._load_key(tenant_id, user_id)
            reqs = val.setdefault("requested_folders", [])
            if clean_path and clean_path not in reqs:
                reqs.append(clean_path)
            # Remove from disconnected list so it can be re-added
            disconn = [d for d in val.get("disconnected_folders", []) if d != norm_path]
            val["disconnected_folders"] = disconn
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

            disconn = set(str(d).replace("\\", "/").rstrip("/").lower() for d in val.get("disconnected_folders", []))
            folders = []
            total_files = 0
            total_chunks = len([
                c for c in val.get("chunks", [])
                if str(c.get("folder_id", "")).replace("\\", "/").rstrip("/").lower() not in disconn
                and str(c.get("folder_path", "")).replace("\\", "/").rstrip("/").lower() not in disconn
            ])

            for f_dict in val.get("folders", {}).values():
                fid = str(f_dict.get("folder_id") or "").replace("\\", "/").rstrip("/").lower()
                fpath = str(f_dict.get("folder_path") or "").replace("\\", "/").rstrip("/").lower()
                if fid in disconn or fpath in disconn:
                    continue
                total_files += f_dict.get("file_count", 0)
                folders.append(LocalFolderInfo(**f_dict))

            # Resilient fallback to default agent or other tenant agent
            if (not is_online or not folders) and user_id != "default":
                def_val = self._load_key(tenant_id, "default")
                def_disconn = set(str(d).replace("\\", "/").rstrip("/").lower() for d in def_val.get("disconnected_folders", []))
                combined_disconn = disconn.union(def_disconn)
                def_agent = def_val.get("agent", {})
                def_last_ts = def_agent.get("last_heartbeat_ts", 0.0)
                def_online = (time.time() - def_last_ts) < HEARTBEAT_TTL_SECONDS
                def_folders = def_val.get("folders", {})
                if def_online or def_folders:
                    is_online = def_online
                    agent = def_agent
                    folders = []
                    for f_dict in def_folders.values():
                        fid = str(f_dict.get("folder_id") or "").replace("\\", "/").rstrip("/").lower()
                        fpath = str(f_dict.get("folder_path") or "").replace("\\", "/").rstrip("/").lower()
                        if fid in combined_disconn or fpath in combined_disconn:
                            continue
                        folders.append(LocalFolderInfo(**f_dict))
                    total_files = sum(f.file_count for f in folders)
                    total_chunks = len([
                        c for c in def_val.get("chunks", [])
                        if str(c.get("folder_id", "")).replace("\\", "/").rstrip("/").lower() not in combined_disconn
                        and str(c.get("folder_path", "")).replace("\\", "/").rstrip("/").lower() not in combined_disconn
                    ])
            else:
                total_chunks = len([
                    c for c in val.get("chunks", [])
                    if str(c.get("folder_id", "")).replace("\\", "/").rstrip("/").lower() not in disconn
                    and str(c.get("folder_path", "")).replace("\\", "/").rstrip("/").lower() not in disconn
                ])

            # Persistence auto-restore: if no folders in memory, check active_folders.json on disk
            if not folders:
                try:
                    from backend.integrations.files.company_data.persistence import get_persisted_folder
                    persisted = (
                        get_persisted_folder(tenant_id)
                        or get_persisted_folder("enterprise-tenant")
                        or get_persisted_folder("default")
                    )
                    if persisted and persisted.exists() and persisted.is_dir():
                        p_str = str(persisted)
                        p_norm = p_str.replace("\\", "/").rstrip("/").lower()
                        if p_norm not in disconn:
                            f_count = 0
                            try:
                                for _, _, flist in os.walk(persisted):
                                    f_count += len([f for f in flist if not f.startswith(".") and not f.startswith("~$")])
                            except Exception:
                                f_count = 1
                            restored = LocalFolderInfo(
                                folder_id=p_str,
                                folder_path=p_str,
                                display_name=persisted.name or p_str,
                                file_count=f_count,
                                chunk_count=0,
                                status="ready",
                                last_synced_at=datetime.now(timezone.utc).isoformat(),
                            )
                            folders.append(restored)
                            val.setdefault("folders", {})[p_str] = restored.model_dump()
                            total_files = f_count
                            is_online = True
                            self._save_key(tenant_id, user_id, val)
                except Exception as exc:
                    logger.debug("Could not auto-restore persisted folder in get_agent_status: %s", exc)

            # Local computer resilience: if folders physically exist on local disk, local storage is active
            if not is_online and folders:
                for f in folders:
                    try:
                        if Path(f.folder_path).exists() and Path(f.folder_path).is_dir():
                            is_online = True
                            break
                    except Exception:
                        pass

            return {
                "is_online": is_online,
                "last_heartbeat": agent.get("last_heartbeat"),
                "agent_version": agent.get("agent_version") or ("desktop-direct-1.0.0" if is_online else None),
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

            if payload.replace_all:
                # Exclusive folder mode: purge all other folders and chunks across all keys in store
                for other_k in list(self._data.keys()):
                    self._data[other_k]["folders"] = {}
                    self._data[other_k]["chunks"] = []
                val["folders"] = {}
                val["chunks"] = []

            # 1. Update folder registry
            # Do not resync if this exact folder was disconnected
            disconn = set(val.get("disconnected_folders", []))
            fid_norm = str(fid).replace("\\", "/").rstrip("/").lower()
            fpath_norm = str(payload.folder_path).replace("\\", "/").rstrip("/").lower()
            if fid_norm in disconn or fpath_norm in disconn:
                return

            folders = val.setdefault("folders", {})
            prev_folder = folders.get(fid, {})
            prev_file_count = prev_folder.get("file_count", 0)
            prev_chunk_count = prev_folder.get("chunk_count", 0) if not payload.replace_all else 0

            file_count = len(payload.files) if payload.files else prev_file_count
            chunk_count = prev_chunk_count + len(payload.chunks)

            folders[fid] = {
                "folder_id": fid,
                "folder_path": payload.folder_path,
                "display_name": payload.display_name or Path(payload.folder_path).name or fid,
                "file_count": file_count,
                "chunk_count": chunk_count,
                "status": "synced",
                "last_synced_at": now_iso,
            }

            # 2. Replace or append chunks belonging to this folder
            existing_chunks = val.get("chunks", []) if not payload.replace_all else []
            retained_chunks = [c for c in existing_chunks if c.get("folder_id") != fid] if payload.replace_all else list(existing_chunks)

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

            # Keep chunks bounded so PostgreSQL JSONB / memory stays fast and avoids timeouts
            MAX_STORED_CHUNKS = 3000
            if len(retained_chunks) > MAX_STORED_CHUNKS:
                retained_chunks = retained_chunks[-MAX_STORED_CHUNKS:]

            val["chunks"] = retained_chunks
            self._save_key(tenant_id, user_id, val)
            logger.info("Synced %d chunks for local folder '%s' (user %s, total chunks: %d, files: %d)", len(payload.chunks), fid, user_id, chunk_count, file_count)

    def remove_folder(self, tenant_id: str, user_id: str, folder_id: str) -> bool:
        """Remove a connected folder and its chunks across tenant keys, and queue removal to Windows PC agent."""
        import urllib.parse
        clean_fid = urllib.parse.unquote(str(folder_id).strip())
        norm_fid = clean_fid.replace("\\", "/").rstrip("/").lower()
        base_name_fid = norm_fid.split("/")[-1] if "/" in norm_fid else norm_fid

        with self._lock:
            keys_to_clean = [(tenant_id, user_id)]
            if user_id != "default":
                keys_to_clean.append((tenant_id, "default"))
            if tenant_id != "enterprise-tenant":
                keys_to_clean.append(("enterprise-tenant", "default"))
            for k in list(self._data.keys()):
                if k not in keys_to_clean:
                    keys_to_clean.append(k)

            matched = False
            removed_paths = []

            for t_k, u_k in keys_to_clean:
                val = self._load_key(t_k, u_k)
                folders = val.get("folders", {})
                fids_to_del = []
                for fid, f_info in list(folders.items()):
                    f_path = str(f_info.get("folder_path") or fid).strip()
                    norm_path = f_path.replace("\\", "/").rstrip("/").lower()
                    norm_f_id = str(fid).replace("\\", "/").rstrip("/").lower()
                    if (
                        norm_f_id == norm_fid
                        or norm_path == norm_fid
                        or (base_name_fid and (norm_f_id.endswith("/" + base_name_fid) or norm_path.endswith("/" + base_name_fid)))
                        or (norm_fid and (norm_fid in norm_f_id or norm_fid in norm_path or norm_f_id in norm_fid or norm_path in norm_fid))
                    ):
                        fids_to_del.append(fid)
                        removed_paths.append(f_path)

                for fid in fids_to_del:
                    del folders[fid]
                    matched = True

                if fids_to_del or matched or norm_fid:
                    all_del_norms = {norm_fid, *(p.replace("\\", "/").rstrip("/").lower() for p in removed_paths)}
                    # Purge chunks
                    val["chunks"] = [
                        c for c in val.get("chunks", [])
                        if str(c.get("folder_id", "")).replace("\\", "/").rstrip("/").lower() not in all_del_norms
                        and str(c.get("folder_path", "")).replace("\\", "/").rstrip("/").lower() not in all_del_norms
                    ]
                    # Purge requested folders
                    val["requested_folders"] = [
                        r for r in val.get("requested_folders", [])
                        if str(r).replace("\\", "/").rstrip("/").lower() not in all_del_norms
                    ]
                    # Blocklist from resurrecting via agent heartbeat
                    disconn = set(val.get("disconnected_folders", []))
                    disconn.update(all_del_norms)
                    val["disconnected_folders"] = list(disconn)

                    # Queue remove command to Windows local agent
                    cmd_path = removed_paths[0] if removed_paths else clean_fid
                    val.setdefault("pending_commands", []).append({
                        "id": f"cmd_{int(time.time() * 1000)}",
                        "command": "remove_folder",
                        "payload": {"folder_path": cmd_path, "folder_id": clean_fid},
                    })
                    self._save_key(t_k, u_k, val)

            # Bulk update all rows in PostgreSQL if configured
            if self._dsn:
                try:
                    import psycopg
                    from psycopg.rows import dict_row
                    all_del_norms = {norm_fid, *(p.replace("\\", "/").rstrip("/").lower() for p in removed_paths)}
                    if base_name_fid:
                        all_del_norms.add(base_name_fid)
                    with psycopg.connect(self._dsn, autocommit=True, connect_timeout=4, row_factory=dict_row) as conn:
                        rows = conn.execute("SELECT tenant_id, user_id, data FROM public.nanvi_local_agent_store").fetchall()
                        for r in rows:
                            row_t = r["tenant_id"]
                            row_u = r["user_id"]
                            row_data = r.get("data") or {}
                            row_folders = row_data.get("folders", {})
                            row_to_del = []
                            for fid, finfo in list(row_folders.items()):
                                f_p = str(finfo.get("folder_path") or fid).strip().replace("\\", "/").rstrip("/").lower()
                                f_i = str(fid).strip().replace("\\", "/").rstrip("/").lower()
                                if (
                                    f_i == norm_fid
                                    or f_p == norm_fid
                                    or (base_name_fid and (f_i.endswith("/" + base_name_fid) or f_p.endswith("/" + base_name_fid)))
                                    or (norm_fid and (norm_fid in f_i or norm_fid in f_p or f_i in norm_fid or f_p in norm_fid))
                                ):
                                    row_to_del.append(fid)
                            for fid in row_to_del:
                                row_folders.pop(fid, None)
                            row_data["folders"] = row_folders
                            row_data["chunks"] = [
                                c for c in row_data.get("chunks", [])
                                if str(c.get("folder_id", "")).replace("\\", "/").rstrip("/").lower() not in all_del_norms
                                and str(c.get("folder_path", "")).replace("\\", "/").rstrip("/").lower() not in all_del_norms
                            ]
                            disconn_set = set(row_data.get("disconnected_folders", []))
                            disconn_set.update(all_del_norms)
                            row_data["disconnected_folders"] = list(disconn_set)
                            cmd_path = removed_paths[0] if removed_paths else clean_fid
                            row_cmds = row_data.setdefault("pending_commands", [])
                            row_cmds.append({
                                "id": f"cmd_{int(time.time() * 1000)}",
                                "command": "remove_folder",
                                "payload": {"folder_path": cmd_path, "folder_id": clean_fid},
                            })
                            conn.execute(
                                "UPDATE public.nanvi_local_agent_store SET data = %s::jsonb, updated_at = NOW() WHERE tenant_id = %s AND user_id = %s",
                                (json.dumps(row_data), row_t, row_u),
                            )
                except Exception as exc:
                    logger.warning("PostgreSQL remove_folder bulk update error: %s", exc)

            # Clear persisted active folder file so company_data service clears it
            try:
                from backend.integrations.files.company_data.persistence import ACTIVE_FOLDERS_FILE, ACTIVE_FOLDER_FILE
                if ACTIVE_FOLDERS_FILE.exists():
                    ACTIVE_FOLDERS_FILE.write_text("{}", encoding="utf-8")
                if ACTIVE_FOLDER_FILE.exists():
                    ACTIVE_FOLDER_FILE.write_text("{}", encoding="utf-8")
            except Exception:
                pass

            try:
                from backend.integrations.files.company_data_service import CompanyDataService
                cds = CompanyDataService.for_tenant(tenant_id)
                cds.clear_cache()
            except Exception:
                pass

            return True

            return matched or True
    def queue_command(self, tenant_id: str, user_id: str, command: str, payload: dict[str, Any]) -> str:
        """Queue a command (e.g. open_file) to be delivered to user's connected Windows PC agent."""
        cmd_id = f"cmd_{int(time.time() * 1000)}"
        with self._lock:
            val = self._load_key(tenant_id, user_id)
            cmds = val.setdefault("pending_commands", [])
            cmds.append({
                "id": cmd_id,
                "command": command,
                "payload": payload,
                "created_at": datetime.now(timezone.utc).isoformat(),
            })
            self._save_key(tenant_id, user_id, val)
        return cmd_id

    def pop_commands(self, tenant_id: str, user_id: str) -> list[dict[str, Any]]:
        """Retrieve and clear pending commands for the agent on heartbeat."""
        clean_t = str(tenant_id or "default").strip()
        clean_u = str(user_id or "default").strip()

        with self._lock:
            # 1. Exact match for this tenant and user
            val = self._load_key(clean_t, clean_u)
            cmds = list(val.get("pending_commands", []))
            if cmds:
                val["pending_commands"] = []
                self._save_key(clean_t, clean_u, val)
                return cmds

            # 2. Check PostgreSQL directly for ANY pending commands in this tenant
            if self._dsn:
                try:
                    import psycopg
                    from psycopg.rows import dict_row
                    with psycopg.connect(self._dsn, autocommit=True, connect_timeout=3, row_factory=dict_row) as conn:
                        rows = conn.execute(
                            """
                            SELECT user_id, data FROM public.nanvi_local_agent_store 
                            WHERE tenant_id = %s AND (data->>'pending_commands') IS NOT NULL AND jsonb_array_length(data->'pending_commands') > 0
                            LIMIT 5
                            """,
                            (clean_t,),
                        ).fetchall()
                        for r in rows:
                            row_d = r.get("data") or {}
                            row_cmds = list(row_d.get("pending_commands", []))
                            if row_cmds:
                                row_d["pending_commands"] = []
                                conn.execute(
                                    "UPDATE public.nanvi_local_agent_store SET data = %s::jsonb, updated_at = NOW() WHERE tenant_id = %s AND user_id = %s",
                                    (json.dumps(row_d), clean_t, r["user_id"]),
                                )
                                # Update in-memory cache if present
                                k_other = self._key(clean_t, r["user_id"])
                                if k_other in self._data:
                                    self._data[k_other]["pending_commands"] = []
                                return row_cmds
                except Exception as exc:
                    logger.debug("PostgreSQL pop_commands error: %s", exc)

            # 3. Fallback: check in-memory dictionary for this tenant
            for (t, u), d in self._data.items():
                if t == clean_t and d.get("pending_commands"):
                    pending = list(d["pending_commands"])
                    d["pending_commands"] = []
                    self._save_key(t, u, d)
                    return pending

            return []

    def get_all_files(self, tenant_id: str, user_id: str) -> list[dict[str, Any]]:
        """Return all distinct indexed files from connected folders for this user/tenant."""
        with self._lock:
            val = self._load_key(tenant_id, user_id)
            chunks = val.get("chunks", [])
            if not chunks and user_id != "default":
                def_val = self._load_key(tenant_id, "default")
                chunks = def_val.get("chunks", [])
            if not chunks:
                for (t, u), d in list(self._data.items()):
                    if (t == tenant_id or t == "enterprise-tenant" or t == "default") and d.get("chunks"):
                        chunks = d.get("chunks", [])
                        break

            seen = set()
            files: list[dict[str, Any]] = []
            for c in chunks:
                rel = c.get("relative_path", "")
                fname = c.get("filename", Path(rel).name if rel else "document")
                f_name = c.get("folder_name", "")
                f_path = c.get("folder_path", "")
                disp_path = f"{f_name}/{rel}".strip("/") if f_name else rel
                key = (fname.lower(), rel.lower())
                if key in seen:
                    continue
                seen.add(key)

                full_open = ""
                if f_path and rel:
                    full_open = f"{f_path}\\{rel}".replace("/", "\\")
                elif f_path:
                    full_open = f_path
                else:
                    full_open = disp_path

                exact_full_path = full_open if (":" in full_open or full_open.startswith("\\\\")) else (f_path or disp_path)

                files.append({
                    "name": fname,
                    "path": exact_full_path,
                    "full_path": exact_full_path,
                    "display_path": disp_path,
                    "type": Path(fname).suffix.lstrip("."),
                    "modified_at": c.get("modified_at") or "",
                    "open_url": exact_full_path,
                    "source": "local",
                    "content_snippet": (c.get("text") or "")[:350],
                })

            # Disk fallback: if no chunks are synced yet, discover files directly from connected folders on disk
            if not files:
                folders_map = dict(val.get("folders", {}))
                if not folders_map and user_id != "default":
                    folders_map = dict(self._load_key(tenant_id, "default").get("folders", {}))
                if not folders_map:
                    for (t, u), d in list(self._data.items()):
                        if d.get("folders"):
                            folders_map = dict(d.get("folders", {}))
                            break

                for f_info in folders_map.values():
                    fp = f_info.get("folder_path")
                    if fp:
                        p_dir = Path(fp)
                        if p_dir.exists() and p_dir.is_dir():
                            for root, _, flist in os.walk(p_dir):
                                for fn in flist:
                                    if fn.startswith(".") or fn.startswith("~$"):
                                        continue
                                    f_p = Path(root) / fn
                                    try:
                                        rel = str(f_p.relative_to(p_dir)).replace("\\", "/")
                                    except Exception:
                                        rel = fn
                                    key = (fn.lower(), rel.lower())
                                    if key in seen:
                                        continue
                                    seen.add(key)
                                    full_p = str(f_p)
                                    disp = f"{p_dir.name}/{rel}"
                                    mtime_iso = ""
                                    try:
                                        mtime_iso = datetime.fromtimestamp(f_p.stat().st_mtime, tz=timezone.utc).isoformat()
                                    except Exception:
                                        pass
                                    files.append({
                                        "name": fn,
                                        "path": full_p,
                                        "full_path": full_p,
                                        "display_path": disp,
                                        "type": f_p.suffix.lstrip("."),
                                        "modified_at": mtime_iso,
                                        "open_url": full_p,
                                        "source": "local",
                                        "content_snippet": "",
                                    })
            return files

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
            if not chunks and user_id != "default":
                def_val = self._load_key(tenant_id, "default")
                chunks = def_val.get("chunks", [])
            if not chunks:
                for (t, u), d in list(self._data.items()):
                    if (t == tenant_id or t == "enterprise-tenant" or t == "default") and d.get("chunks"):
                        chunks = d.get("chunks", [])
                        break

            if not chunks:
                return []

            query_clean = query.strip().lower()
            raw_terms = [t.lower() for t in re.findall(r"\w+", query) if len(t) > 1]

            STOP_WORDS = {
                "what", "is", "are", "in", "the", "my", "our", "folder", "folders",
                "file", "files", "document", "documents", "tell", "me", "about",
                "can", "you", "summarize", "summary", "explain", "describe", "show",
                "give", "please", "contents", "inside", "do", "we", "have", "there",
                "any", "this", "that", "these", "those", "from", "with", "and", "for"
            }
            content_terms = [t for t in raw_terms if t not in STOP_WORDS]
            query_terms = content_terms if content_terms else raw_terms

            scored: list[tuple[float, dict[str, Any]]] = []

            # If query is general or only contains stop words (e.g. 'summarize my folder', 'what is in my files'),
            # return representative chunks from each distinct file!
            if not content_terms:
                seen_f = set()
                top_distinct = []
                for c in chunks:
                    if folder_id and c.get("folder_id") != folder_id:
                        continue
                    fn = c.get("filename", "")
                    if fn not in seen_f:
                        seen_f.add(fn)
                        top_distinct.append((100.0, c))
                    if len(top_distinct) >= top_k:
                        break
                scored = top_distinct or [(100.0, c) for c in chunks[:top_k]]
            for c in chunks:
                if folder_id and c.get("folder_id") != folder_id:
                    continue

                text_lower = c.get("text", "").lower()
                rel_path_lower = c.get("relative_path", "").lower()
                fn_lower = c.get("filename", "").lower()

                score = 0.0
                matched_terms = 0

                # 1. Exact multi-word phrase bonus
                if len(query_terms) > 1 and query_clean in text_lower:
                    score += 250.0
                    matched_terms += len(query_terms)
                if len(query_terms) > 1 and query_clean in rel_path_lower:
                    score += 350.0
                    matched_terms += len(query_terms)

                # 2. Individual term counts
                for term in query_terms:
                    count_text = text_lower.count(term)
                    count_path = rel_path_lower.count(term)
                    count_fn = fn_lower.count(term)

                    if count_text > 0 or count_path > 0 or count_fn > 0:
                        matched_terms += 1
                        score += (count_text * 1.0) + (count_path * 5.0) + (count_fn * 15.0)

                if matched_terms > 0:
                    coverage = min(1.0, matched_terms / len(query_terms))
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
