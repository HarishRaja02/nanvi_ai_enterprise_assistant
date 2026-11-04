from datetime import datetime
from ..parser import DocumentParser
from ..models import Document
from .common import source_for, metadata_for


class TextParser(DocumentParser):
    extensions = frozenset({
        ".txt", ".text", ".md", ".markdown", ".log",
        ".yaml", ".yml", ".ini", ".cfg", ".conf"
    })

    def parse_bytes(self, *, filename: str, relative_path: str, data: bytes, modified_at: datetime | None = None) -> Document:
        ext = filename.casefold().split(".")[-1] if "." in filename else "txt"
        decoded = None
        for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
            try:
                decoded = data.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        if decoded is None:
            decoded = data.decode("utf-8", errors="replace")
        return Document(source_for(filename, relative_path, ext), metadata_for(len(data), modified_at), decoded, [], [ext.upper()])
