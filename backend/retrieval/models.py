from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class AccessControlMetadata:
    tenant_id: str
    owner_id: str | None = None
    department: str | None = None
    restricted_department: str | None = None
    resource_type: str = "knowledge_source"


@dataclass(frozen=True)
class SourceMetadata:
    source_type: str
    source_id: str
    filename: str | None
    path: str | None
    page: int | None = None
    sheet: str | None = None
    created_at: datetime | None = None
    modified_at: datetime | None = None
    access: AccessControlMetadata = field(default_factory=lambda: AccessControlMetadata(tenant_id=""))
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class KnowledgeChunk:
    chunk_id: str
    content: str
    source: SourceMetadata
    chunk_index: int
    location: str | None = None


@dataclass(frozen=True)
class RetrievalHit:
    chunk: KnowledgeChunk
    score: float
    retrieval_method: str


@dataclass(frozen=True)
class RetrievalRequest:
    query: str
    top_k: int = 10
    candidate_k: int = 30


@dataclass(frozen=True)
class RetrievalResult:
    hits: tuple[RetrievalHit, ...]
