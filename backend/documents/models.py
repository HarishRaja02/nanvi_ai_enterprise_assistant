from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class DocumentSource:
    """Stable source information retained with extracted content."""
    filename: str
    path: str
    file_type: str


@dataclass(frozen=True)
class DocumentMetadata:
    size_bytes: int
    modified_at: datetime | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DocumentTable:
    """A normalized table plus its source location."""
    headers: list[str]
    rows: list[list[str]]
    source_label: str


@dataclass(frozen=True)
class Document:
    """Normalized representation used by later retrieval/AI layers."""
    source: DocumentSource
    metadata: DocumentMetadata
    text: str
    tables: list[DocumentTable] = field(default_factory=list)
    locations: list[str] = field(default_factory=list)

    @property
    def filename(self) -> str:
        return self.source.filename

    @property
    def path(self) -> str:
        return self.source.path
