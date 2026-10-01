"""Indexing models and chunking logic for company data documents."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from backend.core.config import settings
from backend.sources.models import SourceReference

# RAG Relevance Threshold: Higher values indicate stronger match/similarity.
# Chunks scoring below RAG_RELEVANCE_THRESHOLD are deemed low-confidence and pruned.
RAG_RELEVANCE_THRESHOLD = getattr(settings, "rag_relevance_threshold", 25.0)


@dataclass(frozen=True)
class CompanyChunk:
    chunk_id: str
    folder: str
    filename: str
    relative_path: str
    full_path: str
    file_type: str
    location: str
    content: str
    sheet: str | None = None
    page: int | None = None
    folder_path: str = ""
    document_id: str = ""
    document_type: str = ""
    source: str = "local_file"

    def to_metadata(self) -> dict[str, Any]:
        """Structured chunk metadata preserving exact document provenance."""
        return {
            "document_id": self.document_id or self.relative_path,
            "filename": self.filename,
            "file_path": self.full_path,
            "document_type": self.document_type or self.file_type,
            "page": self.page,
            "sheet": self.sheet,
            "source": self.source,
            "chunk_id": self.chunk_id,
            "folder": self.folder,
            "location": self.location,
        }


@dataclass
class SearchResult:
    is_exact_match: bool
    answer_content: str
    sources: list[SourceReference] = field(default_factory=list)
    top_chunks: list[CompanyChunk] = field(default_factory=list)
    recommended_files: list[dict[str, Any]] = field(default_factory=list)


def chunk_document(
    doc: Any,
    folder: str,
    folder_path: str,
    filename: str,
    rel_path: str,
    full_path: str,
    file_type: str,
) -> list[CompanyChunk]:
    """Chunk a parsed document into structured CompanyChunk segments."""
    chunks: list[CompanyChunk] = []
    text = doc.text.strip()
    if not text:
        return chunks

    is_upload = "upload" in folder.casefold() or "upload" in rel_path.casefold()
    source_type_val = "upload" if is_upload else "local_file"

    # PDF with pages
    if file_type == "pdf" and "[Page " in text:
        pages = re.split(r"(?m)^\[Page (\d+)\]\n", text)
        if len(pages) > 1:
            idx = 1
            while idx < len(pages):
                page_num = int(pages[idx])
                content = pages[idx + 1].strip() if idx + 1 < len(pages) else ""
                if content:
                    chunks.append(CompanyChunk(
                        chunk_id=f"{rel_path}:page-{page_num}",
                        folder=folder,
                        filename=filename,
                        relative_path=rel_path,
                        full_path=full_path,
                        file_type=file_type,
                        location=f"Page {page_num}",
                        content=content,
                        page=page_num,
                        folder_path=folder_path,
                        document_id=rel_path,
                        document_type=file_type,
                        source=source_type_val,
                    ))
                idx += 2
            return chunks

    # Excel with sheets
    if file_type == "xlsx" and "[Sheet " in text:
        sheets = re.split(r"(?m)^\[Sheet (.+?)\]\n", text)
        if len(sheets) > 1:
            idx = 1
            while idx < len(sheets):
                sheet_name = sheets[idx].strip()
                content = sheets[idx + 1].strip() if idx + 1 < len(sheets) else ""
                if content:
                    chunks.append(CompanyChunk(
                        chunk_id=f"{rel_path}:sheet-{sheet_name}",
                        folder=folder,
                        filename=filename,
                        relative_path=rel_path,
                        full_path=full_path,
                        file_type=file_type,
                        location=f"Sheet: {sheet_name}",
                        content=content,
                        sheet=sheet_name,
                        folder_path=folder_path,
                        document_id=rel_path,
                        document_type=file_type,
                        source=source_type_val,
                    ))
                idx += 2
            return chunks

    # DOCX / CSV / Text: split by logical paragraphs or table sections
    sections = [s.strip() for s in text.split("\n\n") if len(s.strip()) > 20]
    if not sections:
        sections = [text]

    for i, sec in enumerate(sections, start=1):
        chunks.append(CompanyChunk(
            chunk_id=f"{rel_path}:sec-{i}",
            folder=folder,
            filename=filename,
            relative_path=rel_path,
            full_path=full_path,
            file_type=file_type,
            location=f"Section {i}",
            content=sec,
            folder_path=folder_path,
            document_id=rel_path,
            document_type=file_type,
            source=source_type_val,
        ))
    return chunks
