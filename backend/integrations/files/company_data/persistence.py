"""Active folder persistence across server restarts and per-tenant configurations."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

PROJECT_STORAGE_FILE = Path(__file__).resolve().parents[4] / "storage" / "active_folders.json"
BACKEND_STORAGE_FILE = Path(__file__).resolve().parents[3] / "storage" / "active_folders.json"
ACTIVE_FOLDERS_FILE = PROJECT_STORAGE_FILE
ACTIVE_FOLDER_FILE = Path(__file__).resolve().parents[4] / "storage" / "active_folder.json"
BACKEND_ACTIVE_FOLDER_FILE = Path(__file__).resolve().parents[3] / "storage" / "active_folder.json"


def _is_valid_dir(path_str: str | None) -> bool:
    if not path_str or not isinstance(path_str, str):
        return False
    norm = path_str.replace("\\", "/").lower()
    if "/var/task" in norm or "var/task" in norm or "pytest" in norm or not path_str.strip():
        return False
    try:
        p = Path(path_str).resolve()
        return p.exists() and p.is_dir()
    except Exception:
        return False


def get_persisted_folder(tenant_id: str = "default") -> Path | None:
    """Read the last chosen active folder path for the given tenant from persistent storage."""
    t_id = (tenant_id or "default").strip()
    candidate_files = [PROJECT_STORAGE_FILE, BACKEND_STORAGE_FILE, ACTIVE_FOLDER_FILE, BACKEND_ACTIVE_FOLDER_FILE]

    for f in candidate_files:
        try:
            if not f.exists():
                continue
            data = json.loads(f.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                continue

            # 1. Direct tenant match
            t_data = data.get(t_id)
            if isinstance(t_data, dict) and _is_valid_dir(t_data.get("path")):
                return Path(t_data["path"]).resolve()

            # 2. enterprise-tenant match
            ent_data = data.get("enterprise-tenant")
            if isinstance(ent_data, dict) and _is_valid_dir(ent_data.get("path")):
                return Path(ent_data["path"]).resolve()

            # 3. Default tenant match
            def_data = data.get("default")
            if isinstance(def_data, dict) and _is_valid_dir(def_data.get("path")):
                return Path(def_data["path"]).resolve()

            # 4. Top-level path object (e.g. active_folder.json)
            top_path = data.get("path")
            if _is_valid_dir(top_path):
                return Path(top_path).resolve()

            # 5. Fallback to newest valid folder across all tenants
            for _, tinfo in sorted(data.items(), key=lambda item: item[1].get("updated_at", "") if isinstance(item[1], dict) else "", reverse=True):
                if isinstance(tinfo, dict) and _is_valid_dir(tinfo.get("path")):
                    return Path(tinfo["path"]).resolve()
        except Exception as exc:
            logger.debug("Could not read persisted folder file %s: %s", f, exc)

    return None


def set_persisted_folder(path: Path | str, tenant_id: str = "default") -> None:
    """Save active folder path for the given tenant to persistent storage."""
    t_id = (tenant_id or "default").strip()
    try:
        resolved = Path(path).resolve()
        path_str = str(resolved)
        now_iso = datetime.now(timezone.utc).isoformat()

        for target_file in (PROJECT_STORAGE_FILE, BACKEND_STORAGE_FILE):
            try:
                target_file.parent.mkdir(parents=True, exist_ok=True)
                all_data: dict[str, Any] = {}
                if target_file.exists():
                    try:
                        all_data = json.loads(target_file.read_text(encoding="utf-8"))
                        if not isinstance(all_data, dict):
                            all_data = {}
                    except Exception:
                        all_data = {}

                record = {"path": path_str, "updated_at": now_iso}
                all_data[t_id] = record
                all_data["default"] = record
                all_data["enterprise-tenant"] = record
                target_file.write_text(json.dumps(all_data, indent=2), encoding="utf-8")
            except Exception as e:
                logger.debug("Could not write to %s: %s", target_file, e)

        for single_file in (ACTIVE_FOLDER_FILE, BACKEND_ACTIVE_FOLDER_FILE):
            try:
                single_file.parent.mkdir(parents=True, exist_ok=True)
                single_file.write_text(
                    json.dumps({"path": path_str, "updated_at": now_iso}, indent=2),
                    encoding="utf-8",
                )
            except Exception:
                pass

        logger.info("Persisted active company data folder for tenant '%s': %s", t_id, path_str)
    except Exception as exc:
        logger.warning("Could not persist active folder path for tenant '%s': %s", t_id, exc)
