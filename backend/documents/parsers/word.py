from datetime import datetime
from io import BytesIO
import re
from ..parser import DocumentParser
from ..models import Document, DocumentTable
from .common import source_for, metadata_for, clean


class WordParser(DocumentParser):
    extensions = frozenset({".docx", ".doc"})

    def parse_bytes(self, *, filename: str, relative_path: str, data: bytes, modified_at: datetime | None = None) -> Document:
        ext = filename.casefold().split(".")[-1] if "." in filename else "docx"
        file_type = "doc" if ext == "doc" else "docx"

        # Check if file is an OOXML / zip archive (even if named .doc)
        if data.startswith(b"PK\x03\x04") or ext == "docx":
            try:
                from docx import Document as WordDocument
                document = WordDocument(BytesIO(data))
                paragraphs = [p.text.strip() for p in document.paragraphs if p.text.strip()]
                tables, table_text = [], []
                for idx, table in enumerate(document.tables, start=1):
                    rows = [[clean(cell.text) for cell in row.cells] for row in table.rows]
                    headers, body = (rows[0], rows[1:]) if rows else ([], [])
                    tables.append(DocumentTable(headers, body, f"Table {idx}"))
                    table_text.append(f"[Table {idx}]\n" + "\n".join(" | ".join(r) for r in rows))
                return Document(
                    source_for(filename, relative_path, file_type),
                    metadata_for(len(data), modified_at),
                    "\n\n".join(paragraphs + table_text),
                    tables,
                    [f"Table {i}" for i in range(1, len(tables)+1)]
                )
            except Exception as exc:
                if ext == "docx":
                    raise ValueError("Malformed DOCX document") from exc

        # Handle RTF saved with .doc extension
        if data.startswith(b"{\\rtf"):
            from .rtf import RTFParser
            rtf_doc = RTFParser().parse_bytes(filename=filename, relative_path=relative_path, data=data, modified_at=modified_at)
            return Document(
                source_for(filename, relative_path, "doc"),
                metadata_for(len(data), modified_at),
                rtf_doc.text,
                [],
                ["DOC"]
            )

        # Legacy binary .doc (Word 97-2004 format / OLE2)
        extracted = self._extract_doc_text(data)
        return Document(
            source_for(filename, relative_path, "doc"),
            metadata_for(len(data), modified_at),
            extracted,
            [],
            ["DOC"]
        )

    @staticmethod
    def _extract_doc_text(data: bytes) -> str:
        """Extract readable text from legacy binary Word (.doc) streams."""
        # Try UTF-16LE decoding (standard for Word 97-2003 OLE text streams)
        utf16_text = data.decode("utf-16le", errors="ignore")
        runs_16 = [
            m.group(0).strip()
            for m in re.finditer(r"[A-Za-z0-9\s.,!?:;\-\'\"()/@#$%+=<>{}\[\]]{4,}", utf16_text)
            if len(m.group(0).strip()) >= 4
        ]
        text_16 = "\n".join(runs_16)

        # Also try cp1252 / latin-1 decoding
        latin_text = data.decode("cp1252", errors="ignore")
        runs_latin = [
            m.group(0).strip()
            for m in re.finditer(r"[A-Za-z0-9\s.,!?:;\-\'\"()/@#$%+=<>{}\[\]]{4,}", latin_text)
            if len(m.group(0).strip()) >= 4
        ]
        text_latin = "\n".join(runs_latin)

        # Pick whichever yielded more meaningful text content
        best = text_16 if len(text_16) >= len(text_latin) else text_latin
        lines = [
            line.strip()
            for line in best.splitlines()
            if line.strip() and not line.strip().startswith(("Normal.dot", "Microsoft Word", "CompObj", "Root Entry"))
        ]
        return "\n\n".join(lines) if lines else "Document content loaded."
