from datetime import datetime
from ..parser import DocumentParser
from ..models import Document
from .common import source_for, metadata_for

class TextParser(DocumentParser):
    extensions = frozenset({".txt", ".md"})
    def parse_bytes(self, *, filename: str, relative_path: str, data: bytes, modified_at: datetime | None = None) -> Document:
        decoded = None
        for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
            try:
                decoded = data.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        if decoded is None:
            decoded = data.decode("utf-8", errors="replace")
        return Document(source_for(filename, relative_path, "txt"), metadata_for(len(data), modified_at), decoded, [], ["TXT"])
