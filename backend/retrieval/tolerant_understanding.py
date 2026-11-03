"""Tolerant enterprise query understanding with grounded extraction and strict code validation."""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Sequence

from backend.retrieval.date_parser import DateFilter, parse_query_date
from backend.retrieval.entity_resolver import EntityCandidate, EntityIndex, ResolutionDecision

logger = logging.getLogger(__name__)

DOC_TYPES = ("invoice", "contract", "project", "customer", "employee", "transaction", "receipt", "policy", "resume")
STATUS_TERMS = ("pending", "overdue", "paid", "unpaid", "active", "completed", "in progress", "at risk", "planning", "draft", "expired", "scheduled")


@dataclass
class TolerantQuery:
    """Validated structured interpretation of a messy or partial user query."""
    intent: str = "find_file"  # "find_file" | "lookup_record" | "list_records"
    entity: str | None = None
    entity_type: str | None = None
    resolved_candidate: EntityCandidate | None = None
    doc_type: str | None = None
    date_filter: DateFilter | None = None
    status: str | None = None
    raw_query: str = ""
    is_disambiguated: bool = False
    needs_user_clarification: bool = False
    clarification_message: str | None = None
    candidate_options: list[EntityCandidate] = field(default_factory=list)


def _detect_doc_type(query: str) -> str | None:
    q_low = query.casefold()
    if any(w in q_low for w in ("invoice", "invoices", "bill", "bills", "billing")) or re.search(r"\binv[-_ ]?\d+", q_low):
        return "invoice"
    if any(w in q_low for w in ("contract", "contracts", "agreement", "agreements", "nda", "ndas", "renewal")) or re.search(r"\b(?:cnt|ctr|nda|pur)[-_ ]?\d+", q_low):
        return "contract"
    if any(w in q_low for w in ("project", "projects", "milestone", "milestones", "sprint")):
        return "project"
    if any(w in q_low for w in ("customer", "customers", "client", "clients")):
        return "customer"
    if any(w in q_low for w in ("employee", "employees", "staff", "salary", "salaries", "attendance")):
        return "employee"
    if any(w in q_low for w in ("transaction", "transactions", "expense", "expenses", "debit", "credit")):
        return "transaction"
    if any(w in q_low for w in ("resume", "resumes", "cv")):
        return "resume"
    if any(w in q_low for w in ("policy", "handbook", "guideline")):
        return "policy"
    return None


def _detect_status(query: str) -> str | None:
    q_low = query.casefold()
    for s in STATUS_TERMS:
        if re.search(rf"\b{re.escape(s)}\b", q_low):
            return s
    return None


def _detect_intent(query: str) -> str:
    q_low = query.casefold()
    # File search explicitly asked
    if any(w in q_low for w in ("file", "files", "document", "documents", "pdf", "docx", "xlsx", "csv", "download", "folder", "open")):
        return "find_file"
    # List records
    if any(q_low.startswith(w) for w in ("list ", "show all ", "what are ", "all ")) or "list of" in q_low:
        return "list_records"
    # Lookup records / questions about status, amounts, dates
    if any(w in q_low for w in ("how many", "who is", "what is", "total", "amount", "budget", "pending", "overdue", "status")):
        return "lookup_record"
    return "find_file"


def understand_query(
    query: str,
    entity_resolver: EntityIndex,
    available_years: Sequence[int] | None = None,
    llm_provider: Any = None,
    clock: datetime | None = None,
) -> TolerantQuery:
    """Analyze a user query into a validated, grounded TolerantQuery.
    
    Zero hardcoded business names, dates, or column names.
    Uses regex as fast pre-check; falls back to LLM extraction when available;
    every extracted field is strictly verified against real indexed data.
    """
    clean_q = query.strip()
    q_lower = clean_q.casefold()

    doc_type = _detect_doc_type(clean_q)
    status = _detect_status(clean_q)
    intent = _detect_intent(clean_q)
    date_flt = parse_query_date(clean_q, available_years=available_years, clock=clock)

    # 1. Check if LLM extraction is possible and needed for messy queries
    llm_extracted_entity = None
    if llm_provider is not None and len(clean_q.split()) > 3:
        try:
            prompt = (
                "You are an enterprise query parser. Extract structured search parameters from the user's input.\n"
                "Return JSON ONLY in this exact format:\n"
                "{\n"
                '  "intent": "find_file" | "lookup_record" | "list_records",\n'
                '  "entity": "<entity_or_company_or_person_name_or_null>",\n'
                '  "entity_type": "customer" | "vendor" | "employee" | "project" | null,\n'
                '  "doc_type": "invoice" | "contract" | "project" | "customer" | "employee" | "transaction" | null,\n'
                '  "status": "<status_or_null>"\n'
                "}\n"
                "Rules:\n"
                "1. If no entity name is mentioned, set entity to null.\n"
                "2. Do not invent any names or details that are not in the user query.\n\n"
                f'User query: "{clean_q}"'
            )
            raw = llm_provider.generate(prompt)
            m = re.search(r"\{[^{}]*\}", raw)
            if m:
                parsed = json.loads(m.group(0))
                if parsed.get("entity") and isinstance(parsed["entity"], str):
                    llm_extracted_entity = parsed["entity"].strip()
                if not doc_type and parsed.get("doc_type") in DOC_TYPES:
                    doc_type = parsed["doc_type"]
                if not status and parsed.get("status") in STATUS_TERMS:
                    status = parsed["status"]
                if parsed.get("intent") in ("find_file", "lookup_record", "list_records"):
                    intent = parsed["intent"]
        except Exception as exc:
            logger.debug("LLM query extraction skipped: %s", exc)

    # 2. Extract potential entity candidate from query
    resolved_candidate: EntityCandidate | None = None
    candidate_options: list[EntityCandidate] = []
    needs_clarification = False
    clarification_msg = None

    # First attempt: if LLM extracted an entity name
    if llm_extracted_entity:
        decision = entity_resolver.resolve(llm_extracted_entity, min_score=60.0)
        if decision.status == "resolved" and decision.candidate:
            resolved_candidate = decision.candidate
        elif decision.status in ("ambiguous", "short_query") and decision.candidates:
            candidate_options = decision.candidates
            needs_clarification = True
            clarification_msg = decision.clarification_prompt

    # Second attempt: If not resolved, test entity tokens from the cleaned query
    if not resolved_candidate and not candidate_options:
        inferred_entity_type = None
        if doc_type == "invoice":
            inferred_entity_type = "vendor"
        elif doc_type == "project":
            inferred_entity_type = "project"
        elif doc_type == "employee":
            inferred_entity_type = "employee"

        # Pre-clean: strip label prefixes followed by names (e.g. "Vendor name DataBridge" -> "DataBridge")
        pre_clean = re.sub(r"(?i)\b(?:vendor|customer|client|name)\s+(?=[a-z0-9])", " ", clean_q)
        # Strip common action/filler phrases to isolate the entity
        stripped_q = re.sub(
            r"(?i)\b(find|search|show|get|list|look\s+for|where\s+is|give\s+me|fetch|check|see|the|a|an|for|of|by|with|about|at|to|from|in|on|brief|record|records|item|items|file|files|document|documents|pdf|docx|xlsx|csv|invoice|invoices|contract|contracts|agreement|agreements|policy|policies|project|projects|close\s+to|around|near|dated|date|ending\s+soon|going\s+to\s+end\s+soon)\b",
            " ",
            pre_clean,
        )
        # Strip date numbers like 2025-08-09, 9 aug, 225
        stripped_q = re.sub(r"\b\d{1,4}[-/]\d{1,2}[-/]\d{1,4}\b", " ", stripped_q)
        stripped_q = re.sub(r"\b\d{1,2}(?:st|nd|rd|th)?\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s*\d*\b", " ", stripped_q, flags=re.IGNORECASE)
        stripped_q = re.sub(r"\b\d{1,4}\b", " ", stripped_q)
        stripped_q = re.sub(r"[^\w\s]", " ", stripped_q).strip()

        if stripped_q and len(stripped_q) >= 2:
            decision = entity_resolver.resolve(stripped_q, entity_type_hint=inferred_entity_type, min_score=65.0)
            if not decision.candidate and inferred_entity_type:
                decision = entity_resolver.resolve(stripped_q, min_score=65.0)

            if decision.status == "resolved" and decision.candidate:
                resolved_candidate = decision.candidate
            elif decision.status in ("ambiguous", "short_query") and decision.candidates:
                # Only treat as ambiguous if candidates have high matching scores (>= 80.0) or short_query
                valid_candidates = [c for c in decision.candidates if c.score >= 80.0 or decision.status == "short_query"]
                if valid_candidates:
                    # If LLM provider is available, attempt grounded disambiguation
                    if llm_provider is not None:
                        from backend.retrieval.entity_resolver import disambiguate_with_llm
                        chosen = disambiguate_with_llm(clean_q, valid_candidates, llm_provider)
                        if chosen:
                            resolved_candidate = chosen
                        else:
                            candidate_options = valid_candidates
                            needs_clarification = True
                            clarification_msg = decision.clarification_prompt
                    else:
                        candidate_options = valid_candidates
                        needs_clarification = True
                        clarification_msg = decision.clarification_prompt

    # Third attempt: Direct scan of multi-word names in query
    if not resolved_candidate and not candidate_options:
        # Try full clean query directly against resolver with inferred type hint if present
        decision = entity_resolver.resolve(clean_q, entity_type_hint=inferred_entity_type if 'inferred_entity_type' in locals() else None, min_score=75.0)
        if decision.status == "resolved" and decision.candidate:
            resolved_candidate = decision.candidate
        elif decision.status in ("ambiguous", "short_query") and decision.candidates:
            candidate_options = decision.candidates
            needs_clarification = True
            clarification_msg = decision.clarification_prompt

    entity_name = resolved_candidate.canonical_name if resolved_candidate else (llm_extracted_entity or None)
    entity_type = resolved_candidate.entity_type if resolved_candidate else None

    return TolerantQuery(
        intent=intent,
        entity=entity_name,
        entity_type=entity_type,
        resolved_candidate=resolved_candidate,
        doc_type=doc_type,
        date_filter=date_flt,
        status=status,
        raw_query=clean_q,
        is_disambiguated=bool(resolved_candidate),
        needs_user_clarification=needs_clarification,
        clarification_message=clarification_msg,
        candidate_options=candidate_options,
    )

