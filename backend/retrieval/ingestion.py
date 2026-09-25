from __future__ import annotations

import hashlib
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any, Callable, Sequence

from backend.documents.models import Document
from backend.documents.parsers import CSVParser, ExcelParser, PDFParser, TextParser, WordParser
from backend.documents.service import DocumentProcessingError, DocumentProcessingService, UnsupportedDocumentTypeError
from backend.integrations.email.models import EmailMessage
from backend.retrieval.metadata_index import FileMetadataIndex, FileRecord
from backend.retrieval.models import AccessControlMetadata, KnowledgeChunk, SourceMetadata

logger = logging.getLogger(__name__)


def source_from_document(document: Document, access: AccessControlMetadata) -> SourceMetadata:
    return SourceMetadata(
        source_type=document.source.file_type,
        source_id=document.source.path,
        filename=document.source.filename,
        path=document.source.path,
        modified_at=document.metadata.modified_at,
        access=access,
        extra={"locations": tuple(document.locations)},
    )


def source_from_email(message: EmailMessage, tenant_id: str, owner_id: str) -> SourceMetadata:
    return SourceMetadata(
        source_type="email",
        source_id=message.id,
        filename=message.subject or message.id,
        path=message.web_link,
        created_at=message.sent_at,
        modified_at=message.received_at,
        access=AccessControlMetadata(tenant_id=tenant_id, owner_id=owner_id, resource_type="email_mailbox"),
        extra={"conversation_id": message.conversation_id, "sender": message.sender.address if message.sender else None},
    )


@dataclass
class IngestionSummary:
    discovered: int = 0
    new_files: int = 0
    updated_files: int = 0
    skipped_files: int = 0
    failed_files: int = 0
    deleted_files: int = 0
    chunks_created: int = 0
    duration_ms: float = 0.0


class IncrementalIngestionPipeline:
    """Production-grade incremental document ingestion pipeline.
    
    Features:
    1. Content-hash (SHA256) and mtime change detection to skip unchanged files.
    2. Concurrency control via atomic execution lock to prevent indexing race conditions.
    3. Graceful handling of corrupted/encrypted/unsupported files (indexing_failed status).
    4. Format-aware chunking preserving sheets (XLSX), pages (PDF), sections (DOCX/CSV).
    5. Clean reconciliation and deletion of removed files.
    """

    SUPPORTED_EXTENSIONS = frozenset({".pdf", ".docx", ".xlsx", ".csv", ".txt", ".md", ".pptx"})
    MAX_FILE_SIZE_BYTES = 25 * 1024 * 1024  # 25 MB max per file
    MAX_FAILED_RETRIES = 3

    def __init__(
        self,
        metadata_index: FileMetadataIndex,
        doc_service: DocumentProcessingService | None = None,
        retrieval_service: Any | None = None,
    ) -> None:
        self.metadata_index = metadata_index
        self._doc_service = doc_service or DocumentProcessingService([
            PDFParser(), WordParser(), ExcelParser(), CSVParser(), TextParser()
        ])
        self._retrieval_service = retrieval_service
        self._lock = Lock()

    def set_retrieval_service(self, service: Any) -> None:
        self._retrieval_service = service

    def ingest_directory(
        self,
        base_dir: Path | str,
        tenant_id: str = "enterprise-tenant",
        force: bool = False,
    ) -> IngestionSummary:
        """Scan directory and incrementally ingest modified/new files.
        
        Thread-safe: uses atomic lock to prevent concurrent ingestion runs.
        """
        if not self._lock.acquire(blocking=False):
            logger.info("Ingestion already in progress, skipping concurrent trigger")
            return IngestionSummary()

        started = time.perf_counter()
        summary = IngestionSummary()

        try:
            root = Path(base_dir).resolve()
            if not root.exists() or not root.is_dir():
                logger.warning("Ingestion root directory does not exist: %s", root)
                return summary

            # Discover all valid files under root (traversing arbitrary depth, no symlinks)
            discovered_files = self._discover_files(root)
            summary.discovered = len(discovered_files)
            active_file_ids = set()

            for dept, subfolder, rel_path, file_path in discovered_files:
                active_file_ids.add(rel_path)
                try:
                    res = self._process_single_file(
                        file_path=file_path,
                        rel_path=rel_path,
                        dept=dept,
                        tenant_id=tenant_id,
                        force=force,
                    )
                    if res == "new":
                        summary.new_files += 1
                    elif res == "updated":
                        summary.updated_files += 1
                    elif res == "skipped":
                        summary.skipped_files += 1
                    elif res == "failed":
                        summary.failed_files += 1
                except Exception as exc:
                    logger.warning("Unhandled error during ingestion of %s: %s", rel_path, exc)
                    summary.failed_files += 1

            # Reconcile deletions: remove records no longer on disk
            existing_records = self.metadata_index.list_all()
            for rec in existing_records:
                if rec.file_id not in active_file_ids:
                    # Check if it was supposed to be in this directory root
                    try:
                        rec_full = Path(rec.full_path).resolve()
                        if root in rec_full.parents or rec_full == root:
                            self.metadata_index.remove(rec.file_id)
                            summary.deleted_files += 1
                    except Exception:
                        pass

            self.metadata_index.save_to_disk()
            summary.duration_ms = round((time.perf_counter() - started) * 1000, 2)
            logger.info(
                "Ingestion completed in %sms: %d discovered, %d new, %d updated, %d skipped, %d failed, %d deleted",
                summary.duration_ms, summary.discovered, summary.new_files, summary.updated_files,
                summary.skipped_files, summary.failed_files, summary.deleted_files,
            )
            return summary

        finally:
            self._lock.release()

    def _discover_files(self, base_root: Path) -> list[tuple[str, str, str, Path]]:
        """Discover supported non-hidden files."""
        discovered: list[tuple[str, str, str, Path]] = []
        known_depts = {"Customers", "Finance", "HR", "Projects", "Contracts", "Resumes", "Uploads"}

        for current_root, dir_names, file_names in os.walk(base_root, followlinks=False):
            # Exclude hidden directories and symlinks
            dir_names[:] = [
                d for d in dir_names
                if not d.startswith(".") and not (Path(current_root) / d).is_symlink()
            ]

            rel_curr = Path(current_root).relative_to(base_root)
            parts = rel_curr.parts

            for name in file_names:
                if name.startswith(".") or name.startswith("~$"):
                    continue
                ext = Path(name).suffix.casefold()
                if ext not in self.SUPPORTED_EXTENSIONS:
                    continue

                full_path = Path(current_root) / name

                from backend.integrations.files.company_data_service import _classify_department
                dept, subfolder = _classify_department(parts, name, base_root.name)

                rel_parts = [dept]
                if subfolder:
                    rel_parts.append(subfolder)
                rel_parts.append(name)
                rel_path = "/".join(rel_parts)

                discovered.append((dept, subfolder, rel_path, full_path))

        return discovered

    def _process_single_file(
        self,
        file_path: Path,
        rel_path: str,
        dept: str,
        tenant_id: str,
        force: bool = False,
    ) -> str:
        """Process a single file incrementally with change detection and fault tolerance."""
        ext = file_path.suffix.casefold().lstrip(".")
        existing = self.metadata_index.get(rel_path)

        stat = file_path.stat()
        file_size = stat.st_size
        mtime = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)

        # File size guard
        if file_size > self.MAX_FILE_SIZE_BYTES:
            logger.warning("File %s exceeds max size limit (%d bytes), skipping", rel_path, file_size)
            if existing:
                existing.status = "indexing_failed"
                existing.error_message = f"Exceeds max file size {self.MAX_FILE_SIZE_BYTES} bytes"
                self.metadata_index.upsert(existing)
            return "failed"

        # Check existing failed retries cap
        if not force and existing and existing.status == "indexing_failed":
            if existing.modified_at == mtime and existing.failed_attempts >= self.MAX_FAILED_RETRIES:
                return "skipped"

        # Fast mtime check
        if not force and existing and existing.status == "indexed":
            if existing.modified_at == mtime and existing.size_bytes == file_size:
                return "skipped"

        # Read bytes and compute hash
        try:
            data = file_path.read_bytes()
        except Exception as exc:
            logger.warning("Could not read file %s: %s", rel_path, exc)
            return "failed"

        content_hash = hashlib.sha256(data).hexdigest()

        # Content hash check
        if not force and existing and existing.status == "indexed":
            if existing.content_hash == content_hash:
                # Update mtime if only timestamps changed
                existing.modified_at = mtime
                self.metadata_index.upsert(existing)
                return "skipped"

        # Parse document with error fallback
        is_new = existing is None
        try:
            doc = self._doc_service.parse_bytes(
                filename=file_path.name,
                relative_path=rel_path,
                data=data,
                modified_at=mtime,
            )
        except (UnsupportedDocumentTypeError, DocumentProcessingError, Exception) as exc:
            logger.warning("Failed to parse file %s: %s", rel_path, exc)
            attempts = (existing.failed_attempts + 1) if existing else 1
            fail_record = FileRecord(
                file_id=rel_path,
                filename=file_path.name,
                normalized_filename=file_path.name.casefold(),
                path=rel_path,
                full_path=str(file_path),
                file_type=ext,
                department=dept,
                size_bytes=file_size,
                modified_at=mtime,
                content_hash=content_hash,
                indexed_at=datetime.now(timezone.utc),
                status="indexing_failed",
                error_message=str(exc),
                failed_attempts=attempts,
            )
            self.metadata_index.upsert(fail_record)
            return "failed"

        # Document parsed successfully: create chunks and index
        preview = doc.text[:300].replace("\n", " ").strip() if doc.text else ""
        record = FileRecord(
            file_id=rel_path,
            filename=file_path.name,
            normalized_filename=file_path.name.casefold(),
            path=rel_path,
            full_path=str(file_path),
            file_type=ext,
            department=dept,
            size_bytes=file_size,
            modified_at=mtime,
            content_hash=content_hash,
            indexed_at=datetime.now(timezone.utc),
            status="indexed",
            error_message=None,
            failed_attempts=0,
            preview=preview,
        )

        # Index chunks in KnowledgeRetrievalService if wired
        if self._retrieval_service is not None and doc.text.strip():
            try:
                access = AccessControlMetadata(
                    tenant_id=tenant_id,
                    department=dept,
                    restricted_department=dept if dept in {"Finance", "HR", "Contracts"} else None,
                    resource_type="company_file",
                )
                chunks = self._retrieval_service.index_document(doc, access)
                record.chunk_ids = [c.chunk_id for c in chunks]
            except Exception as exc:
                logger.warning("Failed to index chunks for %s in retrieval service: %s", rel_path, exc)

        self.metadata_index.upsert(record)
        return "new" if is_new else "updated"
