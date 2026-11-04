from datetime import datetime
from io import BytesIO
import re
from ..parser import DocumentParser
from ..models import Document
from .common import source_for, metadata_for, clean


class PPTXParser(DocumentParser):
    extensions = frozenset({".pptx", ".ppt"})

    def parse_bytes(self, *, filename: str, relative_path: str, data: bytes, modified_at: datetime | None = None) -> Document:
        ext = filename.casefold().split(".")[-1] if "." in filename else "pptx"
        file_type = "ppt" if ext == "ppt" else "pptx"

        if data.startswith(b"PK\x03\x04") or ext == "pptx":
            try:
                from pptx import Presentation
                presentation = Presentation(BytesIO(data))
                chunks, locations = [], []
                for index, slide in enumerate(presentation.slides, start=1):
                    texts = []
                    for shape in slide.shapes:
                        if hasattr(shape, "text"):
                            text = clean(shape.text)
                            if text:
                                texts.append(text)
                    if texts:
                        chunks.append(f"[Slide {index}]\n" + "\n".join(texts))
                        locations.append(f"Slide {index}")
                return Document(
                    source_for(filename, relative_path, file_type),
                    metadata_for(len(data), modified_at),
                    "\n\n".join(chunks),
                    [],
                    locations,
                )
            except Exception as exc:
                if ext == "pptx":
                    raise ValueError("Malformed PPTX document") from exc

        # Legacy .ppt stream parsing
        runs = [
            m.group(0).strip()
            for m in re.finditer(r"[A-Za-z0-9\s.,!?:;\-\'\"()/@#$%+=<>{}\[\]]{4,}", data.decode("latin-1", errors="ignore"))
            if len(m.group(0).strip()) >= 4 and not m.group(0).strip().startswith(("\x00", "PowerPoint Document", "Current User"))
        ]
        text_content = "\n".join(runs) if runs else "Presentation content loaded."
        return Document(
            source_for(filename, relative_path, "ppt"),
            metadata_for(len(data), modified_at),
            f"[Presentation]\n{text_content}",
            [],
            ["Presentation"],
        )
