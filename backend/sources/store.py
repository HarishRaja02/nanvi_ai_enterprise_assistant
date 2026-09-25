from __future__ import annotations

from abc import ABC, abstractmethod
from .models import SourceReference


class SourceReferenceStore(ABC):
    @abstractmethod
    def save(self, reference: SourceReference, owner_id: str, tenant_id: str, source_id: str,
             source_type: str, department: str | None = None,
             restricted_department: str | None = None) -> None:
        raise NotImplementedError

    @abstractmethod
    def get(self, reference_id: str):
        raise NotImplementedError


import json
import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

STORAGE_FILE = Path(__file__).resolve().parent.parent / "storage" / "source_store.json"


def _dict_to_ref(data: dict) -> SourceReference:
    from .models import SourceType
    return SourceReference(
        reference_id=data["reference_id"],
        source_type=SourceType(data.get("source_type", "file")),
        display_name=data.get("display_name", ""),
        title=data.get("title"),
        location=data.get("location"),
        page=data.get("page"),
        sheet=data.get("sheet"),
        timestamp=datetime.fromisoformat(data["timestamp"]) if data.get("timestamp") else None,
        mime_type=data.get("mime_type"),
        href=data.get("href"),
    )


class InMemorySourceReferenceStore(SourceReferenceStore):
    """Development/test store with disk-backed persistence across server reloads."""

    _shared_items: dict[str, dict] = {}

    def __init__(self) -> None:
        self._items = InMemorySourceReferenceStore._shared_items
        self._load_from_disk()

    def _load_from_disk(self) -> None:
        if not STORAGE_FILE.exists():
            return
        try:
            content = json.loads(STORAGE_FILE.read_text(encoding="utf-8"))
            for ref_id, item in content.items():
                if ref_id not in self._items and "reference" in item:
                    try:
                        self._items[ref_id] = {
                            "reference": _dict_to_ref(item["reference"]),
                            "owner_id": item.get("owner_id"),
                            "tenant_id": item.get("tenant_id"),
                            "source_id": item.get("source_id"),
                            "source_type": item.get("source_type"),
                            "department": item.get("department"),
                            "restricted_department": item.get("restricted_department"),
                        }
                    except Exception:
                        pass
        except Exception as exc:
            logger.debug("Could not load source references from disk: %s", exc)

    def _flush_to_disk(self) -> None:
        try:
            STORAGE_FILE.parent.mkdir(parents=True, exist_ok=True)
            data = {}
            for ref_id, item in self._items.items():
                ref = item.get("reference")
                ref_dict = ref.to_frontend_dict() if hasattr(ref, "to_frontend_dict") else dict(ref)
                data[ref_id] = {
                    "reference": ref_dict,
                    "owner_id": item.get("owner_id"),
                    "tenant_id": item.get("tenant_id"),
                    "source_id": item.get("source_id"),
                    "source_type": item.get("source_type"),
                    "department": item.get("department"),
                    "restricted_department": item.get("restricted_department"),
                }
            STORAGE_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception as exc:
            logger.debug("Could not persist source references to disk: %s", exc)

    def save(self, reference, owner_id, tenant_id, source_id, source_type,
             department=None, restricted_department=None):
        self._items[reference.reference_id] = {
            "reference": reference,
            "owner_id": owner_id,
            "tenant_id": tenant_id,
            "source_id": source_id,
            "source_type": source_type,
            "department": department,
            "restricted_department": restricted_department,
        }
        self._flush_to_disk()

    def get(self, reference_id: str):
        item = self._items.get(reference_id)
        if not item and STORAGE_FILE.exists():
            self._load_from_disk()
            item = self._items.get(reference_id)
        return item

