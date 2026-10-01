from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Iterable

from backend.integrations.files.models import FileRecord


class FileRepository(ABC):
    """Filesystem-neutral contract consumed by FileService."""

    @abstractmethod
    def list_files(self, relative_directory: str) -> Iterable[FileRecord]:
        raise NotImplementedError

    @abstractmethod
    def search_by_filename(self, relative_directory: str, query: str) -> Iterable[FileRecord]:
        raise NotImplementedError

    @abstractmethod
    def get_metadata(self, relative_path: str) -> FileRecord:
        raise NotImplementedError

    @abstractmethod
    def read_file(self, relative_path: str) -> bytes:
        raise NotImplementedError
