from __future__ import annotations
import re
from .models import KnowledgeChunk, SourceMetadata


class DocumentChunker:
    """Converts normalized source text into bounded chunks without changing source metadata."""

    def __init__(self, max_chars: int = 1200, overlap: int = 150):
        if max_chars <= 0 or overlap < 0 or overlap >= max_chars:
            raise ValueError("overlap must be >= 0 and smaller than max_chars")
        self.max_chars = max_chars
        self.overlap = overlap

    def chunk(self, text: str, source: SourceMetadata) -> list[KnowledgeChunk]:
        text = text.strip()
        if not text:
            return []
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
        pieces: list[str] = []
        current = ""
        for paragraph in paragraphs:
            if len(paragraph) <= self.max_chars:
                if current and len(current) + 2 + len(paragraph) > self.max_chars:
                    pieces.append(current)
                    current = ""
                current = paragraph if not current else f"{current}\n\n{paragraph}"
            else:
                if current:
                    pieces.append(current); current = ""
                start = 0
                while start < len(paragraph):
                    end = min(start + self.max_chars, len(paragraph))
                    pieces.append(paragraph[start:end])
                    if end == len(paragraph):
                        break
                    start = end - self.overlap
        if current:
            pieces.append(current)

        chunks = []
        for i, piece in enumerate(pieces):
            chunks.append(KnowledgeChunk(
                chunk_id=f"{source.source_id}:{i}", content=piece,
                source=source, chunk_index=i, location=source.extra.get("location")
            ))
        return chunks
