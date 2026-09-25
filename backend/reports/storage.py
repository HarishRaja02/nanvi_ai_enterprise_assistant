from __future__ import annotations

import hashlib
import json
import os
import secrets
import tempfile
from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID

from .models import ReportMetadata


class ReportNotFound(FileNotFoundError):
    pass


class ReportStorage(ABC):
    @abstractmethod
    def save(self, report_id: str, extension: str, source_path: Path, metadata: ReportMetadata) -> ReportMetadata:
        raise NotImplementedError

    @abstractmethod
    def get(self, report_id: str) -> ReportMetadata:
        raise NotImplementedError

    @abstractmethod
    def open_path(self, metadata: ReportMetadata) -> Path:
        raise NotImplementedError

    @abstractmethod
    def issue_download_token(self, report_id: str, ttl_seconds: int) -> tuple[str, ReportMetadata]:
        raise NotImplementedError

    @abstractmethod
    def consume_download_token(self, report_id: str, token: str) -> ReportMetadata:
        raise NotImplementedError


class SecureFileReportStorage(ReportStorage):
    """Private filesystem storage; callers receive IDs/tokens, never filesystem paths."""

    def __init__(self, root: str | Path, clock=None) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(self.root, 0o700)
        except OSError:
            pass
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    @staticmethod
    def _validate_report_id(report_id: str) -> None:
        try:
            UUID(report_id)
        except (ValueError, AttributeError) as exc:
            raise ReportNotFound("Invalid report ID") from exc

    def _meta_path(self, report_id: str) -> Path:
        self._validate_report_id(report_id)
        return self.root / f"{report_id}.json"

    def _data_path(self, storage_name: str) -> Path:
        path = (self.root / storage_name).resolve()
        if self.root not in path.parents:
            raise ReportNotFound("Invalid report storage path")
        return path

    def save(self, report_id, extension, source_path, metadata):
        storage_name = f"{report_id}.{extension}"
        destination = self._data_path(storage_name)
        with tempfile.NamedTemporaryFile(dir=self.root, prefix=f".{report_id}-", suffix=".tmp", delete=False) as tmp:
            tmp_path = Path(tmp.name)
        try:
            with source_path.open("rb") as src, tmp_path.open("wb") as dst:
                while chunk := src.read(1024 * 1024):
                    dst.write(chunk)
            os.replace(tmp_path, destination)
            try:
                os.chmod(destination, 0o600)
            except OSError:
                pass
            saved = ReportMetadata(**{**metadata.__dict__, "storage_name": storage_name, "size_bytes": destination.stat().st_size})
            self._write_metadata(saved)
            return saved
        finally:
            tmp_path.unlink(missing_ok=True)

    def get(self, report_id):
        path = self._meta_path(report_id)
        if not path.is_file():
            raise ReportNotFound("Report not found")
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            data["format"] = data["format"]
            data["created_at"] = datetime.fromisoformat(data["created_at"])
            if data.get("expires_at"):
                data["expires_at"] = datetime.fromisoformat(data["expires_at"])
            from .models import ReportFormat
            data["format"] = ReportFormat(data["format"])
            data["lineage"] = tuple(self._lineage_from_dict(item) for item in data.get("lineage", []))
            return ReportMetadata(**data)
        except (OSError, ValueError, TypeError, KeyError) as exc:
            raise ReportNotFound("Invalid report metadata") from exc

    @staticmethod
    def _lineage_from_dict(item):
        from backend.analysis.models import DataLineage
        return DataLineage(**item)

    def open_path(self, metadata):
        path = self._data_path(metadata.storage_name)
        if not path.is_file():
            raise ReportNotFound("Report file not found")
        return path

    def issue_download_token(self, report_id, ttl_seconds):
        if ttl_seconds < 1 or ttl_seconds > 3600:
            raise ValueError("Download token TTL must be between 1 and 3600 seconds")
        metadata = self.get(report_id)
        token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        expires_at = self._clock() + timedelta(seconds=ttl_seconds)
        updated = ReportMetadata(**{**metadata.__dict__, "download_token_hash": token_hash, "expires_at": expires_at, "downloaded": False})
        self._write_metadata(updated)
        return token, updated

    def consume_download_token(self, report_id, token):
        metadata = self.get(report_id)
        if not metadata.download_token_hash or not metadata.expires_at:
            raise ReportNotFound("Download token is invalid")
        if self._clock() >= metadata.expires_at:
            raise ReportNotFound("Download token has expired")
        expected = hashlib.sha256(token.encode()).hexdigest()
        if not secrets.compare_digest(expected, metadata.download_token_hash):
            raise ReportNotFound("Download token is invalid")
        # One-time token: invalidate before the file is served.
        updated = ReportMetadata(**{**metadata.__dict__, "download_token_hash": None, "expires_at": None, "downloaded": True})
        self._write_metadata(updated)
        return updated

    def _write_metadata(self, metadata):
        payload = dict(metadata.__dict__)
        payload["format"] = metadata.format.value
        payload["created_at"] = metadata.created_at.isoformat()
        payload["expires_at"] = metadata.expires_at.isoformat() if metadata.expires_at else None
        payload["lineage"] = [dict(item.__dict__) for item in metadata.lineage]
        path = self._meta_path(metadata.report_id)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        try:
            os.chmod(tmp, 0o600)
        except OSError:
            pass
        os.replace(tmp, path)
