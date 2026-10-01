from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any

from backend.analysis.models import DataLineage


class ReportFormat(StrEnum):
    EXCEL = "xlsx"
    PDF = "pdf"
    WORD = "docx"
    POWERPOINT = "pptx"
    TEXT = "txt"


@dataclass(frozen=True)
class ReportRequest:
    report_id: str
    title: str
    format: ReportFormat
    generated_by: str
    tenant_id: str
    data: Any
    lineage: tuple[DataLineage, ...] = ()
    description: str | None = None


@dataclass(frozen=True)
class ReportMetadata:
    report_id: str
    title: str
    format: ReportFormat
    owner_id: str
    tenant_id: str
    storage_name: str
    created_at: datetime
    size_bytes: int
    lineage: tuple[DataLineage, ...] = ()
    expires_at: datetime | None = None
    download_token_hash: str | None = field(default=None, repr=False)
    downloaded: bool = False


@dataclass(frozen=True)
class ReportArtifact:
    metadata: ReportMetadata
    download_url: str
