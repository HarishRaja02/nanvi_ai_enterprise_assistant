from datetime import datetime
from io import BytesIO
from ..parser import DocumentParser
from ..models import Document
from .common import source_for, metadata_for

class PDFParser(DocumentParser):
    extensions = frozenset({".pdf"})
    def parse_bytes(self, *, filename: str, relative_path: str, data: bytes, modified_at: datetime | None = None) -> Document:
        try:
            from pypdf import PdfReader
            reader = PdfReader(BytesIO(data))
        except Exception as exc:
            raise ValueError("Malformed PDF document") from exc
        chunks, locations = [], []
        for index, page in enumerate(reader.pages, start=1):
            try:
                text = (page.extract_text() or "").strip()
            except Exception as exc:
                raise ValueError("Malformed PDF document") from exc
            if text:
                chunks.append(f"[Page {index}]\n{text}")
                locations.append(f"Page {index}")
        metadata = reader.metadata or {}
        return Document(source_for(filename, relative_path, "pdf"),
                        metadata_for(len(data), modified_at, pdf_metadata={k: str(v) for k, v in metadata.items()}),
                        "\n\n".join(chunks), [], locations)
