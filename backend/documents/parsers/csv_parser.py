import csv
from datetime import datetime
from io import StringIO
from ..parser import DocumentParser
from ..models import Document, DocumentTable
from .common import source_for, metadata_for, clean

class CSVParser(DocumentParser):
    extensions = frozenset({".csv"})
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
        rows = [[clean(v) for v in row] for row in csv.reader(StringIO(decoded))]
        rows = [r for r in rows if any(r)]
        headers, body = (rows[0], rows[1:]) if rows else ([], [])
        table = DocumentTable(headers=headers, rows=body, source_label="CSV")
        return Document(source_for(filename, relative_path, "csv"), metadata_for(len(data), modified_at),
                        "[CSV]\n" + "\n".join(" | ".join(r) for r in rows), [table], ["CSV"])
