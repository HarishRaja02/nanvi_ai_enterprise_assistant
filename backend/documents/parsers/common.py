from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from ..models import DocumentMetadata, DocumentSource


def source_for(filename: str, relative_path: str, file_type: str) -> DocumentSource:
    return DocumentSource(filename=filename, path=relative_path, file_type=file_type)


def metadata_for(size_bytes: int, modified_at: datetime | None = None, **extra: Any) -> DocumentMetadata:
    return DocumentMetadata(size_bytes=size_bytes, modified_at=modified_at or datetime.now(timezone.utc), extra=extra)


def clean(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()
