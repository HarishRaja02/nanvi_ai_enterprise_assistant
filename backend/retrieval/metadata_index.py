from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any, Iterable, Sequence

logger = logging.getLogger(__name__)


def _normalize_token(text: str) -> str:
    """Normalize text into lowercase alphanumeric tokens."""
    return re.sub(r"[^\w\s]", " ", text.casefold()).strip()


def _tokenize(text: str) -> list[str]:
    return [w for w in re.findall(r"[a-zA-Z0-9_]+", text.casefold()) if len(w) > 0]


@dataclass
class FileRecord:
    """Enterprise file metadata record for the fast deterministic metadata index."""
    file_id: str
    filename: str
    normalized_filename: str
    path: str
    full_path: str
    file_type: str
    department: str
    size_bytes: int
    modified_at: datetime
    content_hash: str
    indexed_at: datetime
    owner: str | None = None
    status: str = "indexed"  # "indexed", "indexing", "indexing_failed", "skipped"
    error_message: str | None = None
    failed_attempts: int = 0
    chunk_ids: list[str] = field(default_factory=list)
    preview: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["modified_at"] = self.modified_at.isoformat()
        d["indexed_at"] = self.indexed_at.isoformat()
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FileRecord:
        d = dict(data)
        d["modified_at"] = datetime.fromisoformat(d["modified_at"])
        d["indexed_at"] = datetime.fromisoformat(d["indexed_at"])
        return cls(**d)


class FileMetadataIndex:
    """Fast, thread-safe, persistent file metadata index.
    
    Provides sub-millisecond deterministic file discovery by filename, path,
    department, extension, and tokens without invoking any LLM.
    """

    def __init__(self, persistence_path: Path | None = None) -> None:
        self._lock = RLock()
        self._records: dict[str, FileRecord] = {}
        self._by_dept: dict[str, set[str]] = {}
        self._by_ext: dict[str, set[str]] = {}
        self._by_token: dict[str, set[str]] = {}
        self._persistence_path = persistence_path
        if self._persistence_path and self._persistence_path.exists():
            self._load_from_disk()

    def upsert(self, record: FileRecord) -> None:
        with self._lock:
            # Clean up prior indexes if record already existed
            if record.file_id in self._records:
                self._remove_indexes(record.file_id)

            self._records[record.file_id] = record

            dept_key = record.department.casefold()
            self._by_dept.setdefault(dept_key, set()).add(record.file_id)

            ext_key = record.file_type.casefold().lstrip(".")
            self._by_ext.setdefault(ext_key, set()).add(record.file_id)

            # Index filename and path tokens
            name_tokens = _tokenize(record.filename) + _tokenize(record.path)
            for t in set(name_tokens):
                self._by_token.setdefault(t, set()).add(record.file_id)

    def remove(self, file_id: str) -> None:
        with self._lock:
            if file_id in self._records:
                self._remove_indexes(file_id)
                del self._records[file_id]

    def _remove_indexes(self, file_id: str) -> None:
        old = self._records.get(file_id)
        if not old:
            return
        dept_key = old.department.casefold()
        if dept_key in self._by_dept:
            self._by_dept[dept_key].discard(file_id)
        ext_key = old.file_type.casefold().lstrip(".")
        if ext_key in self._by_ext:
            self._by_ext[ext_key].discard(file_id)
        tokens = _tokenize(old.filename) + _tokenize(old.path)
        for t in set(tokens):
            if t in self._by_token:
                self._by_token[t].discard(file_id)

    def get(self, file_id: str) -> FileRecord | None:
        with self._lock:
            return self._records.get(file_id)

    def list_all(self) -> list[FileRecord]:
        with self._lock:
            return list(self._records.values())

    def total_count(self) -> int:
        with self._lock:
            return len(self._records)

    def find_by_department(self, department: str) -> list[FileRecord]:
        with self._lock:
            ids = self._by_dept.get(department.casefold(), set())
            return [self._records[fid] for fid in ids if fid in self._records]

    def find_by_extension(self, extension: str) -> list[FileRecord]:
        with self._lock:
            ext_clean = extension.casefold().lstrip(".")
            ids = self._by_ext.get(ext_clean, set())
            return [self._records[fid] for fid in ids if fid in self._records]

    def search_files(
        self,
        query: str,
        department_filter: str | None = None,
        limit: int = 10,
    ) -> list[tuple[float, FileRecord]]:
        """Search files using deterministic filename, extension, path, and keyword matching.
        
        Returns scored results (higher score = stronger match).
        """
        query_clean = query.strip()
        if not query_clean or limit <= 0:
            return []

        q_lower = query_clean.casefold()
        q_tokens = _tokenize(query_clean)
        if not q_tokens:
            return []

        # Filter out common filler query words
        stopwords = {
            "find", "the", "a", "an", "where", "is", "show", "me", "get", "give",
            "file", "files", "document", "documents", "folder", "all", "please",
            "what", "which", "look", "for", "in", "at", "to", "of", "and", "or",
        }
        content_tokens = [w for w in q_tokens if w not in stopwords] or q_tokens

        with self._lock:
            # Fast candidate gathering
            candidate_ids: set[str] = set()
            for t in content_tokens:
                if t in self._by_token:
                    candidate_ids.update(self._by_token[t])

            # If no token match, check substring in filename across all records
            if not candidate_ids:
                for fid, rec in self._records.items():
                    if any(t in rec.normalized_filename for t in content_tokens):
                        candidate_ids.add(fid)

            if not candidate_ids:
                return []

            scored: list[tuple[float, FileRecord]] = []
            for fid in candidate_ids:
                rec = self._records.get(fid)
                if not rec or rec.status == "indexing_failed":
                    continue

                if department_filter and rec.department.casefold() != department_filter.casefold():
                    continue

                score = 0.0
                fn_lower = rec.filename.casefold()
                path_lower = rec.path.casefold()
                stem_lower = rec.filename.rsplit(".", 1)[0].casefold()

                # 1. Exact full filename match (+100.0)
                if fn_lower == q_lower or stem_lower == q_lower:
                    score += 100.0

                # 2. Entire query phrase in filename (+50.0)
                if len(q_lower) > 3 and q_lower in fn_lower:
                    score += 50.0

                # 3. Match individual significant query tokens in filename
                fn_tokens_set = set(_tokenize(rec.filename))
                matched_tokens = 0
                for t in content_tokens:
                    if t in fn_tokens_set:
                        matched_tokens += 1
                        score += 15.0
                    elif t in fn_lower:
                        matched_tokens += 1
                        score += 10.0
                    elif t in path_lower:
                        score += 4.0

                # Token coverage bonus
                if content_tokens:
                    coverage = matched_tokens / len(content_tokens)
                    score += coverage * 30.0

                # 4. Department match bonus (+10.0)
                if rec.department.casefold() in q_lower:
                    score += 10.0

                # 5. Extension match bonus (+8.0)
                if rec.file_type.casefold() in q_lower:
                    score += 8.0

                if score > 0.0:
                    scored.append((score, rec))

            scored.sort(key=lambda item: item[0], reverse=True)
            return scored[:limit]

    def save_to_disk(self) -> None:
        """Persist index state to disk."""
        if not self._persistence_path:
            return
        with self._lock:
            try:
                self._persistence_path.parent.mkdir(parents=True, exist_ok=True)
                data = {
                    "version": 1,
                    "saved_at": datetime.now(timezone.utc).isoformat(),
                    "records": [rec.to_dict() for rec in self._records.values()],
                }
                tmp_path = self._persistence_path.with_suffix(".tmp")
                tmp_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
                # Atomic rename
                if os.name == "nt" and self._persistence_path.exists():
                    self._persistence_path.unlink()
                tmp_path.rename(self._persistence_path)
            except Exception as exc:
                logger.warning("Could not persist FileMetadataIndex to disk: %s", exc)

    def _load_from_disk(self) -> None:
        """Load persisted index state from disk."""
        if not self._persistence_path or not self._persistence_path.exists():
            return
        try:
            content = self._persistence_path.read_text(encoding="utf-8")
            data = json.loads(content)
            records = data.get("records", [])
            for item in records:
                try:
                    rec = FileRecord.from_dict(item)
                    self.upsert(rec)
                except Exception as exc:
                    logger.debug("Skipping invalid persisted record: %s", exc)
            logger.info("Loaded %d file records from persisted index %s", len(self._records), self._persistence_path)
        except Exception as exc:
            logger.warning("Failed to load persisted metadata index: %s", exc)
