"""Active folder persistence across server restarts and per-tenant configurations."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

ACTIVE_FOLDERS_FILE = Path(__file__).resolve().parent.parent.parent.parent / "storage" / "active_folders.json"
ACTIVE_FOLDER_FILE = Path(__file__).resolve().parent.parent.parent.parent / "storage" / "active_folder.json"


def get_persisted_folder(tenant_id: str = "default") -> Path | None:
    """Read the last chosen active folder path for the given tenant from persistent storage."""
    t_id = (tenant_id or "default").strip()
    try:
        if ACTIVE_FOLDERS_FILE.exists():
            data = json.loads(ACTIVE_FOLDERS_FILE.read_text(encoding="utf-8"))
            tenant_data = data.get(t_id)
            if tenant_data:
                saved = tenant_data.get("path")
                if saved and Path(saved).exists() and Path(saved).is_dir():
                    return Path(saved).resolve()
            if t_id != "default":
                default_data = data.get("default")
                if default_data:
                    saved = default_data.get("path")
                    if saved and Path(saved).exists() and Path(saved).is_dir():
                        return Path(saved).resolve()

            # Fallback to the latest saved folder from any tenant
            for _, tinfo in sorted(data.items(), key=lambda item: item[1].get("updated_at", ""), reverse=True):
                saved = tinfo.get("path")
                if saved and Path(saved).exists() and Path(saved).is_dir():
                    return Path(saved).resolve()

        if ACTIVE_FOLDER_FILE.exists():
            data = json.loads(ACTIVE_FOLDER_FILE.read_text(encoding="utf-8"))
            saved = data.get("path")
            if saved and Path(saved).exists() and Path(saved).is_dir():
                return Path(saved).resolve()
    except Exception as exc:
        logger.warning("Could not read persisted folder path for tenant '%s': %s", t_id, exc)
    return None


def set_persisted_folder(path: Path | str, tenant_id: str = "default") -> None:
    """Save active folder path for the given tenant to persistent storage."""
    t_id = (tenant_id or "default").strip()
    try:
        path_str = str(Path(path).resolve())
        ACTIVE_FOLDERS_FILE.parent.mkdir(parents=True, exist_ok=True)
        all_data: dict[str, Any] = {}
        if ACTIVE_FOLDERS_FILE.exists():
            try:
                all_data = json.loads(ACTIVE_FOLDERS_FILE.read_text(encoding="utf-8"))
            except Exception:
                all_data = {}
        now_iso = datetime.now(timezone.utc).isoformat()
        all_data[t_id] = {
            "path": path_str,
            "updated_at": now_iso,
        }
        all_data["default"] = {
            "path": path_str,
            "updated_at": now_iso,
        }
        ACTIVE_FOLDERS_FILE.write_text(json.dumps(all_data, indent=2), encoding="utf-8")
        try:
            ACTIVE_FOLDER_FILE.write_text(
                json.dumps({"path": path_str, "updated_at": now_iso}, indent=2),
                encoding="utf-8",
            )
        except Exception:
            pass
        logger.info("Persisted active company data folder for tenant '%s': %s", t_id, path)
    except Exception as exc:
        logger.warning("Could not persist active folder path for tenant '%s': %s", t_id, exc)
