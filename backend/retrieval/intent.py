from __future__ import annotations

import re
from enum import StrEnum


class QueryIntent(StrEnum):
    FILE_SEARCH = "file_search"
    KNOWLEDGE_QA = "knowledge_qa"
    DIRECTORY_LISTING = "directory_listing"
    AMBIGUOUS_SEARCH = "ambiguous_search"


def classify_retrieval_intent(query: str) -> QueryIntent:
    """Classify user query into deterministic file search, directory listing, or knowledge Q&A."""
    clean = query.strip()
    q_lower = clean.casefold()

    # 1. Directory listing check
    listing_patterns = (
        "list all files", "list files", "show all files", "what files do i have",
        "show all documents", "files in companydata", "files in company data",
        "what files are present", "see files", "available files", "file list",
        "browse files", "list documents", "show documents", "all files",
    )
    if any(p in q_lower for p in listing_patterns):
        return QueryIntent.DIRECTORY_LISTING

    # 2. File extension check: e.g. "report.pdf", "data.xlsx", ".csv"
    if re.search(r"\b[\w-]+\.(pdf|docx|xlsx|csv|txt|md|pptx)\b", q_lower):
        return QueryIntent.FILE_SEARCH

    # 3. Explicit file search / discovery patterns
    file_discovery_prefixes = (
        "find the file", "find file", "find files", "find the report", "find report",
        "find the document", "find document", "find documents", "find the spreadsheet",
        "find spreadsheet", "find the sheet", "find the pdf", "find the doc",
        "find the notes", "find the policy", "find the handbook",
        "where is the", "where are the", "where is our", "where can i find", "where are our",
        "show me the file", "show the file", "show me the document", "show the document",
        "show me the report", "show the report", "show me the spreadsheet", "show the spreadsheet",
        "show me the finance document", "show the finance document",
        "which document contains", "which file contains", "which spreadsheet contains",
        "which folder contains", "what document contains", "what file contains",
        "locate the file", "locate file", "locate document", "locate the report",
        "search for the file", "search for file", "search file", "search for document",
    )
    if any(q_lower.startswith(p) or f" {p}" in q_lower for p in file_discovery_prefixes):
        return QueryIntent.FILE_SEARCH

    # Ambiguous search patterns like "find the latest report", "find the revenue report"
    if q_lower.startswith("find ") and any(k in q_lower for k in ("report", "document", "file", "spreadsheet", "sheet")):
        return QueryIntent.FILE_SEARCH

    return QueryIntent.KNOWLEDGE_QA
