"""Deictic Reference & Contextual Follow-up Resolver — Milestone 7.

Resolves pronouns, deictic references, ordinals, and elliptical follow-ups against
the centralized ConversationContext and ui_entity_index.

Implements Section 7.8 and Section 16 (Milestone 7) of docs/NANVI_SPEC.md:
- "Why?" -> resolves to the active topic / metric drivers
- "Only enterprise" -> resolves to elliptical filter on prior query
- "Open the second one" / "customer #2" -> resolves via ui_entity_index
- "What's the total on this invoice?" -> resolves using active_document / active_entity
"""
from __future__ import annotations

import re
from typing import Any, Sequence

from backend.chat.context_engine import ConversationContext


_ORDINALS = {
    "first": 1,
    "1st": 1,
    "second": 2,
    "2nd": 2,
    "third": 3,
    "3rd": 3,
    "fourth": 4,
    "4th": 4,
    "fifth": 5,
    "5th": 5,
    "last": -1,
}


class DeicticResolver:
    """Resolves deictic, ordinal, elliptical, and causal queries into concrete queries."""

    @classmethod
    def resolve(
        cls,
        query: str,
        context: ConversationContext | None,
        prior_user_query: str = "",
        prior_assistant_answer: str = "",
    ) -> str:
        """Resolve query using conversation context and prior interaction."""
        if not query or not query.strip():
            return query

        clean_q = query.strip()
        q_lower = clean_q.casefold().rstrip("?.!")

        if not context and not prior_user_query:
            return clean_q

        # 1. Causal follow-up: "Why?", "Why is that?", "Why did it change/fall/rise?"
        if q_lower in ("why", "why?", "why is that", "why did that happen", "how come", "what caused this", "why is it"):
            return cls._resolve_why(prior_user_query, prior_assistant_answer)

        # 2. Ordinal references: "Open the second one", "customer #2", "the 3rd one"
        ordinal_resolved = cls._resolve_ordinal(clean_q, context)
        if ordinal_resolved != clean_q:
            return ordinal_resolved

        # 3. Active document / entity deictic reference: "this invoice", "that contract", "on this file"
        deictic_entity_resolved = cls._resolve_active_entity_reference(clean_q, context)
        if deictic_entity_resolved != clean_q:
            return deictic_entity_resolved

        # 4. Elliptical filter / refinement: "Only enterprise", "Just marketing", "For Q3"
        elliptical_resolved = cls._resolve_elliptical(clean_q, prior_user_query)
        if elliptical_resolved != clean_q:
            return elliptical_resolved

        return clean_q

    @classmethod
    def _resolve_why(cls, prior_user_query: str, prior_assistant_answer: str) -> str:
        """Resolve 'Why?' against the prior query topic."""
        if not prior_user_query:
            return "What are the primary drivers and root causes?"

        p_clean = prior_user_query.strip().rstrip("?.!")
        p_lower = p_clean.lower()

        if any(k in p_lower for k in ("revenue", "sales", "earnings", "income", "profit")):
            return f"Why did revenue change? What are the primary revenue drivers and factors behind: {p_clean}?"
        if any(k in p_lower for k in ("invoice", "billing", "payment", "overdue")):
            return f"What is the reason or status explanation behind: {p_clean}?"
        if any(k in p_lower for k in ("employee", "attrition", "turnover", "hiring")):
            return f"What are the reasons and contributing factors for: {p_clean}?"

        return f"What is the explanation and reason behind: {p_clean}?"

    @classmethod
    def _resolve_ordinal(cls, query: str, context: ConversationContext | None) -> str:
        """Resolve ordinal references like 'the second one', 'customer #2' using ui_entity_index."""
        if not context or not context.ui_entity_index:
            return query

        # Match pattern: (open|view|show|check|select|get)? (the)? (first|second|third|fourth|fifth|1st|2nd|3rd|4th|5th|#\d+|\d+)(st|nd|rd|th)? (one|customer|item|invoice|document|file)?
        m = re.search(
            r"\b(?:the\s+)?(first|second|third|fourth|fifth|1st|2nd|3rd|4th|5th|#\d+|\d+)\s*(?:one|customer|item|invoice|document|file|record|row)?\b",
            query,
            re.IGNORECASE,
        )
        if not m:
            return query

        ordinal_token = m.group(1).lower().lstrip("#")
        index = _ORDINALS.get(ordinal_token)
        if index is None:
            try:
                index = int(ordinal_token)
            except ValueError:
                return query

        # Look up in ui_entity_index
        index_str = str(index)
        entity = (
            context.ui_entity_index.get(index_str)
            or context.ui_entity_index.get(f"item_{index_str}")
            or context.ui_entity_index.get(f"customer_{index_str}")
            or context.ui_entity_index.get(f"invoice_{index_str}")
            or context.ui_entity_index.get(f"source_{index_str}")
        )

        if not entity:
            return query

        entity_name = entity.get("name") or entity.get("title") or entity.get("id") or entity.get("filename")
        if not entity_name:
            return query

        # Replace the matched ordinal phrase with the concrete entity name
        matched_span = m.group(0)
        resolved = query.replace(matched_span, str(entity_name))
        # Ensure query asks to view or retrieve details if it was just an elliptical reference like "the second one"
        if resolved.strip() == entity_name:
            return f"Show details for {entity_name}"
        return resolved

    @classmethod
    def _resolve_active_entity_reference(cls, query: str, context: ConversationContext | None) -> str:
        """Resolve 'this invoice', 'that contract', 'this file', 'on this document' to active context."""
        if not context:
            return query

        q = query

        # 1. Document / File deictic reference
        if context.active_document and context.active_document.filename:
            doc_name = context.active_document.filename
            doc_pattern = re.compile(r"\b(?:this|that|the)\s+(?:invoice|contract|document|file|report|pdf|statement)\b", re.IGNORECASE)
            if doc_pattern.search(q):
                q = doc_pattern.sub(doc_name, q)
                return q

        # 2. Entity deictic reference
        if context.active_entity and (context.active_entity.name or context.active_entity.id):
            ent_name = context.active_entity.name or context.active_entity.id
            ent_type = context.active_entity.type or "entity"
            ent_pattern = re.compile(rf"\b(?:this|that|the)\s+(?:{re.escape(ent_type)}|one|account|customer|client|item)\b", re.IGNORECASE)
            if ent_pattern.search(q):
                q = ent_pattern.sub(ent_name, q)
                return q

        return q

    @classmethod
    def _resolve_elliptical(cls, query: str, prior_user_query: str) -> str:
        """Resolve elliptical refinements such as 'Only enterprise', 'In Q3', 'For marketing'."""
        if not prior_user_query:
            return query

        q_clean = query.strip()
        q_lower = q_clean.casefold()

        # Check for elliptical filter markers
        elliptical_starters = ("only ", "just ", "in ", "for ", "by ", "with ", "filter by ", "where ")
        is_short = len(q_clean.split()) <= 4

        if is_short and any(q_lower.startswith(s) for s in elliptical_starters):
            # Combine prior query with the filter
            base = prior_user_query.strip().rstrip("?.!")
            return f"{base}, {q_clean}"

        return query

    @classmethod
    def build_ui_entity_index(cls, ui_specs: Sequence[Any], sources: Sequence[Any] = ()) -> dict[str, Any]:
        """Construct a 1-indexed ui_entity_index dictionary from rendered UI specs and sources."""
        index: dict[str, Any] = {}

        # 1. Index rows from table card
        for spec in ui_specs:
            spec_dict = spec.model_dump() if hasattr(spec, "model_dump") else spec
            card_type = spec_dict.get("card_type")
            data = spec_dict.get("data", {})

            if card_type == "table_card" and "rows" in data:
                rows = data["rows"]
                for idx, row in enumerate(rows[:10], start=1):
                    # Find candidate name or id in row keys
                    name_key = next((k for k in row.keys() if any(sub in k.lower() for sub in ("name", "customer", "client", "title", "vendor", "account"))), None)
                    id_key = next((k for k in row.keys() if any(sub in k.lower() for sub in ("id", "code", "number", "#"))), None)

                    name_val = str(row[name_key]) if name_key else None
                    id_val = str(row[id_key]) if id_key else None

                    item = {
                        "index": idx,
                        "name": name_val or id_val or f"Item {idx}",
                        "id": id_val or "",
                        "raw": row,
                    }
                    index[str(idx)] = item
                    if name_val:
                        index[f"customer_{idx}"] = item

        # 2. Index sources
        for idx, src in enumerate(sources[:10], start=1):
            src_dict = src.to_frontend_dict() if hasattr(src, "to_frontend_dict") else getattr(src, "__dict__", {})
            title = src_dict.get("title") or src_dict.get("filename") or src_dict.get("reference_id")
            if title and str(idx) not in index:
                index[str(idx)] = {
                    "index": idx,
                    "title": title,
                    "name": title,
                    "id": src_dict.get("reference_id", ""),
                    "file_type": src_dict.get("file_type", ""),
                }

        return index
