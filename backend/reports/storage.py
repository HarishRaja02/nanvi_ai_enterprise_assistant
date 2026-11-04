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


import base64
import logging

logger = logging.getLogger(__name__)


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
    """Private filesystem storage with optional persistent cloud database sync for Vercel."""

    def __init__(self, root: str | Path, clock=None, dsn: str | None = None) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(self.root, 0o700)
        except OSError:
            pass
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        if dsn is None:
            try:
                from backend.core.config import settings
                if not getattr(settings, "is_testing", False):
                    dsn = settings.supabase_database_url or settings.database_url
            except Exception:
                dsn = None
        self._dsn = dsn
        self._schema_ensured = False

    def _get_db_connection(self):
        if not self._dsn:
            return None
        try:
            import psycopg
            return psycopg.connect(self._dsn, connect_timeout=1)
        except Exception as exc:
            logger.debug("Database connection skipped in report storage: %s", exc)
            self._dsn = None
            return None

    def _ensure_db_schema(self) -> None:
        if not self._dsn or self._schema_ensured:
            return
        try:
            conn = self._get_db_connection()
            if not conn:
                return
            with conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        CREATE TABLE IF NOT EXISTS nanvi_reports (
                            report_id VARCHAR(64) PRIMARY KEY,
                            tenant_id VARCHAR(64) NOT NULL,
                            owner_id VARCHAR(64) NOT NULL,
                            title VARCHAR(255) NOT NULL,
                            format VARCHAR(16) NOT NULL,
                            storage_name VARCHAR(255) NOT NULL,
                            size_bytes BIGINT NOT NULL,
                            content_base64 TEXT NOT NULL,
                            metadata_json TEXT NOT NULL,
                            download_token_hash VARCHAR(64),
                            expires_at TIMESTAMPTZ,
                            created_at TIMESTAMPTZ DEFAULT NOW(),
                            downloaded BOOLEAN DEFAULT FALSE
                        );
                    """)
            self._schema_ensured = True
        except Exception as exc:
            logger.debug("Could not verify report db schema: %s", exc)

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

            # Persist to cloud database for cross-container Vercel execution
            if self._dsn:
                try:
                    file_bytes = destination.read_bytes()
                    b64_content = base64.b64encode(file_bytes).decode("ascii")
                    payload = dict(saved.__dict__)
                    payload["format"] = saved.format.value
                    payload["created_at"] = saved.created_at.isoformat()
                    payload["expires_at"] = saved.expires_at.isoformat() if saved.expires_at else None
                    payload["lineage"] = [dict(item.__dict__) for item in saved.lineage]
                    meta_json = json.dumps(payload, ensure_ascii=False)

                    self._ensure_db_schema()
                    conn = self._get_db_connection()
                    if conn:
                        with conn:
                            with conn.cursor() as cur:
                                cur.execute("""
                                    INSERT INTO nanvi_reports (
                                        report_id, tenant_id, owner_id, title, format,
                                        storage_name, size_bytes, content_base64, metadata_json,
                                        download_token_hash, expires_at, created_at, downloaded
                                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                                    ON CONFLICT (report_id) DO UPDATE SET
                                        content_base64 = EXCLUDED.content_base64,
                                        metadata_json = EXCLUDED.metadata_json,
                                        size_bytes = EXCLUDED.size_bytes;
                                """, (
                                    saved.report_id, saved.tenant_id, saved.owner_id, saved.title,
                                    saved.format.value, saved.storage_name, saved.size_bytes,
                                    b64_content, meta_json, saved.download_token_hash,
                                    saved.expires_at, saved.created_at, saved.downloaded,
                                ))
                except Exception as exc:
                    logger.warning("Cloud database report backup skipped: %s", exc)

            return saved
        finally:
            tmp_path.unlink(missing_ok=True)

    def _sync_from_db(self, report_id: str) -> ReportMetadata | None:
        """Fetch report metadata and content from cloud DB if missing from local ephemeral /tmp."""
        if not self._dsn:
            return None
        try:
            self._ensure_db_schema()
            conn = self._get_db_connection()
            if not conn:
                return None
            with conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT metadata_json, content_base64, storage_name, download_token_hash, expires_at, downloaded
                        FROM nanvi_reports
                        WHERE report_id = %s;
                    """, (report_id,))
                    row = cur.fetchone()
                    if not row:
                        return None
                    meta_json, b64_content, storage_name, db_token_hash, db_expires_at, db_downloaded = row
                    data = json.loads(meta_json)
                    data["created_at"] = datetime.fromisoformat(data["created_at"])
                    if db_expires_at is not None:
                        data["expires_at"] = db_expires_at if isinstance(db_expires_at, datetime) else datetime.fromisoformat(str(db_expires_at))
                    elif data.get("expires_at"):
                        data["expires_at"] = datetime.fromisoformat(data["expires_at"])
                    if db_token_hash is not None:
                        data["download_token_hash"] = db_token_hash
                    if db_downloaded is not None:
                        data["downloaded"] = bool(db_downloaded)
                    from .models import ReportFormat
                    data["format"] = ReportFormat(data["format"])
                    data["lineage"] = tuple(self._lineage_from_dict(item) for item in data.get("lineage", []))
                    meta = ReportMetadata(**data)

                    # Reconstruct files on local disk
                    self._write_metadata(meta)
                    if b64_content and storage_name:
                        dest = self._data_path(storage_name)
                        if not dest.is_file():
                            dest.write_bytes(base64.b64decode(b64_content))
                    return meta
        except Exception as exc:
            logger.debug("Could not sync report from DB: %s", exc)
            return None

    def get(self, report_id):
        path = self._meta_path(report_id)
        if not path.is_file():
            synced = self._sync_from_db(report_id)
            if synced is not None:
                return synced
            raise ReportNotFound("Report not found")
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
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
            self._sync_from_db(metadata.report_id)
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

        if self._dsn:
            try:
                conn = self._get_db_connection()
                if conn:
                    with conn:
                        with conn.cursor() as cur:
                            cur.execute("""
                                UPDATE nanvi_reports
                                SET download_token_hash = %s, expires_at = %s, downloaded = FALSE
                                WHERE report_id = %s;
                            """, (token_hash, expires_at, report_id))
            except Exception as exc:
                logger.debug("Database token update skipped: %s", exc)

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

        if self._dsn:
            try:
                conn = self._get_db_connection()
                if conn:
                    with conn:
                        with conn.cursor() as cur:
                            cur.execute("""
                                UPDATE nanvi_reports
                                SET download_token_hash = NULL, expires_at = NULL, downloaded = TRUE
                                WHERE report_id = %s;
                            """, (report_id,))
            except Exception as exc:
                logger.debug("Database token invalidation skipped: %s", exc)

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
