"""Content-First Company Data Service (backward-compatible facade).

All implementations are modularized under `backend.integrations.files.company_data.*`:
- `company_data.classification`: Department classification and RBAC mappings.
- `company_data.discovery`: Directory scanning and file listing.
- `company_data.extraction`: Multi-format parsing and structured record extractors.
- `company_data.indexing`: Chunking, chunk models, and relevance scoring thresholds.
- `company_data.persistence`: Active folder storage across restarts.
- `company_data.service`: Main orchestrator `CompanyDataService`.
"""
from __future__ import annotations

from backend.integrations.files.company_data import (
    ACTIVE_FOLDER_FILE,
    ACTIVE_FOLDERS_FILE,
    FOLDER_ROLES,
    RAG_RELEVANCE_THRESHOLD,
    STOP_WORDS,
    STOPWORDS,
    CompanyChunk,
    CompanyDataService,
    SearchResult,
    _classify_department,
    build_directory_listing,
    chunk_document,
    create_default_document_service,
    discover_files,
    extract_contract_records_from_files,
    extract_invoice_records_from_files,
    get_persisted_folder,
    resolve_root,
    set_persisted_folder,
)

__all__ = [
    "CompanyDataService",
    "CompanyChunk",
    "SearchResult",
    "RAG_RELEVANCE_THRESHOLD",
    "FOLDER_ROLES",
    "STOPWORDS",
    "STOP_WORDS",
    "chunk_document",
    "discover_files",
    "resolve_root",
    "build_directory_listing",
    "extract_invoice_records_from_files",
    "extract_contract_records_from_files",
    "create_default_document_service",
    "get_persisted_folder",
    "set_persisted_folder",
    "ACTIVE_FOLDERS_FILE",
    "ACTIVE_FOLDER_FILE",
    "_classify_department",
]
