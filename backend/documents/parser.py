from abc import ABC, abstractmethod
from datetime import datetime
from .models import Document

class DocumentParser(ABC):
    extensions: frozenset[str] = frozenset()

    @abstractmethod
    def parse_bytes(self, *, filename: str, relative_path: str, data: bytes,
                    modified_at: datetime | None = None) -> Document:
        raise NotImplementedError

    def supports(self, filename: str) -> bool:
        return any(filename.casefold().endswith(ext) for ext in self.extensions)
