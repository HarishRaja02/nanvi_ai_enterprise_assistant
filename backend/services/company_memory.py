"""Company Memory and Knowledge Profile Service for Nanvi AI Assistant.

Persists and manages company-specific background, policies, mission, products,
and documentation. This memory is dynamically injected into the conversational
LLM system context so the assistant speaks intelligently and interactively
like ChatGPT while possessing deep knowledge of the enterprise it serves.
"""
from __future__ import annotations

import io
import json
import logging
import os
import re
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Primary storage path in workspace storage/, with /tmp fallback for Vercel/serverless
BASE_STORAGE_DIR = (
    Path("/tmp/storage")
    if (os.getenv("VERCEL") or os.getenv("AWS_LAMBDA_FUNCTION_NAME") or os.getenv("VERCEL_ENV"))
    else Path(__file__).resolve().parents[2] / "storage"
)
COMPANY_MEMORY_FILE = BASE_STORAGE_DIR / "company_memory.json"

# Fallback default memory when unconfigured
DEFAULT_MEMORY = {
    "company_name": "Nanvi AI Enterprise",
    "tagline": "Next-Generation Enterprise AI Copilot & Workplace Intelligence Platform",
    "details": (
        "Nanvi AI is an enterprise workplace assistant designed for secure knowledge management, "
        "document retrieval (RAG), database analytics, and team productivity. "
        "We prioritize Zero-Trust security, strict role-based access control (RBAC), and "
        "intelligent, conversational assistance across company data."
    ),
    "source_type": "default",
    "source_filename": None,
    "updated_at": datetime.now(timezone.utc).isoformat(),
    "updated_by": "system",
    "character_count": 0,
    "word_count": 0,
    "is_configured": False,
}


class CompanyMemoryService:
    """Thread-safe manager for company knowledge memory."""

    _instance: CompanyMemoryService | None = None
    _lock = threading.Lock()

    def __init__(self, storage_file: Path | None = None) -> None:
        self._file = storage_file or COMPANY_MEMORY_FILE
        self._cache: dict[str, Any] | None = None
        self._ensure_storage_dir()

    @classmethod
    def get_instance(cls) -> CompanyMemoryService:
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = CompanyMemoryService()
        return cls._instance

    def _ensure_storage_dir(self) -> None:
        try:
            self._file.parent.mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            logger.warning("Could not create storage directory %s: %s", self._file.parent, exc)

    def get_memory(self, tenant_id: str = "enterprise-tenant") -> dict[str, Any]:
        """Retrieve current company memory."""
        with self._lock:
            if self._cache is not None:
                return dict(self._cache)

            if self._file.exists():
                try:
                    data = json.loads(self._file.read_text(encoding="utf-8"))
                    self._cache = data
                    return dict(data)
                except Exception as exc:
                    logger.warning("Failed to read %s: %s. Using default.", self._file, exc)

            # Fallback to default
            res = dict(DEFAULT_MEMORY)
            res["character_count"] = len(res["details"])
            res["word_count"] = len(res["details"].split())
            self._cache = res
            return res

    def save_memory(
        self,
        details: str,
        company_name: str = "Nanvi AI Enterprise",
        tagline: str = "",
        source_type: str = "pasted",
        source_filename: str | None = None,
        updated_by: str = "admin",
        tenant_id: str = "enterprise-tenant",
    ) -> dict[str, Any]:
        """Save or update company details."""
        clean_details = details.strip()
        clean_name = company_name.strip() or "Nanvi AI Enterprise"
        clean_tagline = tagline.strip()

        with self._lock:
            self._ensure_storage_dir()
            payload = {
                "company_name": clean_name,
                "tagline": clean_tagline,
                "details": clean_details,
                "source_type": source_type,
                "source_filename": source_filename,
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "updated_by": updated_by,
                "character_count": len(clean_details),
                "word_count": len(clean_details.split()) if clean_details else 0,
                "is_configured": bool(clean_details),
            }
            try:
                self._file.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
                self._cache = payload
                logger.info("Successfully persisted company memory (%d characters)", len(clean_details))
            except Exception as exc:
                logger.error("Could not write company memory file %s: %s", self._file, exc)
                raise RuntimeError(f"Failed to persist company memory: {exc}") from exc

            return payload

    def append_memory(
        self,
        additional_details: str,
        source_filename: str | None = None,
        updated_by: str = "admin",
        tenant_id: str = "enterprise-tenant",
    ) -> dict[str, Any]:
        """Append additional content to existing company memory."""
        current = self.get_memory(tenant_id)
        current_text = current.get("details", "")
        new_text = additional_details.strip()

        if current_text and new_text:
            combined = f"{current_text}\n\n---\n### Attached: {source_filename or 'Additional Information'}\n{new_text}"
        else:
            combined = new_text or current_text

        source_type = "combined" if current.get("source_type") in ("pasted", "pdf_upload") else "pdf_upload"
        return self.save_memory(
            details=combined,
            company_name=current.get("company_name", "Nanvi AI Enterprise"),
            tagline=current.get("tagline", ""),
            source_type=source_type,
            source_filename=source_filename or current.get("source_filename"),
            updated_by=updated_by,
            tenant_id=tenant_id,
        )

    def extract_text_from_pdf(self, pdf_bytes: bytes) -> str:
        """Extract clean text from PDF bytes using pypdf."""
        if not pdf_bytes:
            raise ValueError("Empty PDF file provided.")

        try:
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(pdf_bytes))
        except Exception as exc:
            logger.error("Failed to initialize PDF reader: %s", exc)
            raise ValueError("Invalid or corrupted PDF file.") from exc

        pages_text: list[str] = []
        for index, page in enumerate(reader.pages, start=1):
            try:
                page_text = page.extract_text() or ""
                page_text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", page_text)
                page_text = re.sub(r"[ \t]+", " ", page_text).strip()
                if page_text:
                    pages_text.append(f"--- [Page {index}] ---\n{page_text}")
            except Exception as page_exc:
                logger.warning("Could not extract text from page %d: %s", index, page_exc)

        if not pages_text:
            raise ValueError("No readable text could be extracted from this PDF. It may be a scanned image.")

        return "\n\n".join(pages_text)

    def clear_memory(self, updated_by: str = "admin", tenant_id: str = "enterprise-tenant") -> dict[str, Any]:
        """Reset company memory back to baseline."""
        return self.save_memory(
            details="",
            company_name="Nanvi AI Enterprise",
            tagline="",
            source_type="default",
            source_filename=None,
            updated_by=updated_by,
            tenant_id=tenant_id,
        )

    def build_system_context(self, tenant_id: str = "enterprise-tenant") -> str:
        """Construct the prompt injection context with company details."""
        mem = self.get_memory(tenant_id)
        company_name = mem.get("company_name") or "Nanvi AI Enterprise"
        tagline = mem.get("tagline") or ""
        details = mem.get("details") or ""

        if not details.strip():
            return (
                f"You represent {company_name}.\n"
                f"You are Nanvi, their intelligent, highly responsive enterprise AI copilot."
            )

        tagline_line = f"Domain/Tagline: {tagline}\n" if tagline else ""
        return (
            f"=== ENTERPRISE CONTEXT & MEMORY ===\n"
            f"Company Name: {company_name}\n"
            f"{tagline_line}"
            f"Official Company Knowledge & Details:\n"
            f"{details}\n"
            f"=== END OF ENTERPRISE CONTEXT ===\n"
            f"Use the company details above as your core institutional memory. "
            f"When users ask questions about {company_name}, its background, leadership, offerings, "
            f"policies, or mission, answer directly, accurately, and naturally from this memory."
        )


company_memory_service = CompanyMemoryService.get_instance()
