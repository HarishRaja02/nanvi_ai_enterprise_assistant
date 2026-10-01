"""Company data package re-exporting modules and primary interfaces."""
from __future__ import annotations

from backend.integrations.files.company_data.classification import (
    FOLDER_ROLES,
    STOPWORDS,
    _classify_department,
)
from backend.integrations.files.company_data.discovery import (
    build_directory_listing,
    discover_files,
    resolve_root,
)
from backend.integrations.files.company_data.extraction import (
    create_default_document_service,
    extract_contract_records_from_files,
    extract_invoice_records_from_files,
)
from backend.integrations.files.company_data.indexing import (
    RAG_RELEVANCE_THRESHOLD,
    CompanyChunk,
    SearchResult,
    chunk_document,
)
from backend.integrations.files.company_data.persistence import (
    ACTIVE_FOLDER_FILE,
    ACTIVE_FOLDERS_FILE,
    get_persisted_folder,
    set_persisted_folder,
)
from backend.integrations.files.company_data.service import CompanyDataService

STOP_WORDS = STOPWORDS

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
