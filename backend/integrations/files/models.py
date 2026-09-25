from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass(frozen=True)
class FileMetadata:
    relative_path: str
    name: str
    extension: str
    size_bytes: int
    modified_at: datetime
    is_symlink: bool = False


@dataclass(frozen=True)
class FileRecord:
    metadata: FileMetadata
    absolute_path: Path
