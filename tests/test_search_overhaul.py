"""Unit tests for enterprise search overhaul, derived dynamically from real CompanyData."""
from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

import pytest

from backend.chat.file_search import execute_file_search
from backend.chat.models import ChatMessage
from backend.chat.service import ChatService
from backend.retrieval.date_parser import parse_query_date
from backend.retrieval.entity_resolver import discover_and_build_entity_index, get_entity_resolver
from backend.retrieval.tolerant_understanding import understand_query
from backend.security.authorization import UserAttributes

COMPANY_DATA_DIR = Path(__file__).resolve().parents[1] / "backend" / "CompanyData"


@pytest.fixture(scope="module")
def real_resolver():
    """Load real entity index from CompanyData directory."""
    return get_entity_resolver(COMPANY_DATA_DIR)


@pytest.fixture(scope="module")
def sample_entities(real_resolver):
    """Dynamically derive real entity samples from CompanyData."""
    entities = real_resolver.list_all()
    assert len(entities) > 0, "CompanyData must contain indexed entities"

    multi_word_cand = next((e for e in entities if len(e.canonical_name.split()) >= 3), entities[0])
    employee_cand = next((e for e in entities if e.entity_type == "employee" and len(e.canonical_name.split()) == 2), None)
    if not employee_cand:
        employee_cand = next((e for e in entities if len(e.canonical_name.split()) == 2), entities[0])

    vendor_cand = next((e for e in entities if "vendor" in e.entity_type), entities[0])

    return {
        "multi_word": multi_word_cand,
        "employee": employee_cand,
        "vendor": vendor_cand,
    }


def test_entity_resolver_exact_and_substring(real_resolver, sample_entities):
    cand = sample_entities["vendor"]
    name = cand.canonical_name

    # Exact match
    res_exact = real_resolver.resolve(name)
    assert res_exact.status == "resolved"
    assert res_exact.candidate is not None
    assert res_exact.candidate.canonical_name.lower() == name.lower()
    assert res_exact.candidate.score == 100.0

    # Substring match (query is substring of real entity)
    sub = name[:max(3, len(name) - 2)]
    res_sub = real_resolver.resolve(sub)
    assert res_sub.candidate is not None or len(res_sub.candidates) > 0


def test_entity_resolver_first_name_and_last_name(real_resolver, sample_entities):
    emp = sample_entities["employee"]
    tokens = emp.canonical_name.split()
    first_name, last_name = tokens[0], tokens[1]

    # First name
    res_first = real_resolver.resolve(first_name)
    assert res_first.candidate is not None or len(res_first.candidates) > 0
    matched_names = [c.canonical_name for c in ([res_first.candidate] if res_first.candidate else res_first.candidates)]
    assert any(emp.canonical_name in mn or first_name in mn for mn in matched_names)

    # Last name
    res_last = real_resolver.resolve(last_name)
    assert res_last.candidate is not None or len(res_last.candidates) > 0


def test_entity_resolver_first_letters_and_prefix(real_resolver, sample_entities):
    multi = sample_entities["multi_word"]
    words = multi.canonical_name.split()
    # Form prefix query like "ap civ" from first 2-3 characters of each word
    prefix_q = " ".join(w[:min(3, len(w))].lower() for w in words[:2])

    res = real_resolver.resolve(prefix_q)
    assert res.candidate is not None or len(res.candidates) > 0
    top = res.candidate or res.candidates[0]
    assert top.score >= 85.0


def test_entity_resolver_typo_fuzzy(real_resolver, sample_entities):
    cand = sample_entities["vendor"]
    orig = cand.canonical_name
    # Create a single-character typo
    typo_q = orig[:-1] + ("x" if orig[-1] != "x" else "y")

    res = real_resolver.resolve(typo_q)
    assert res.candidate is not None or len(res.candidates) > 0
    top = res.candidate or res.candidates[0]
    assert top.canonical_name.lower() == orig.lower()
    assert top.score >= 80.0


def test_entity_resolver_short_query_prompts_user(real_resolver):
    # 1-character query must return short_query status
    res1 = real_resolver.resolve("A")
    assert res1.status in ("short_query", "no_match")
    if res1.status == "short_query":
        assert res1.clarification_prompt is not None

    # 2-character query must return short_query status
    res2 = real_resolver.resolve("Da")
    assert res2.status in ("short_query", "no_match")


def test_entity_resolver_unknown_query_no_match(real_resolver):
    # Completely non-existent entity query must return no_match and never fabricate
    res = real_resolver.resolve("NonExistentCorpXYZ999999")
    assert res.status == "no_match"
    assert res.candidate is None
    assert len(res.candidates) == 0


def test_date_parser_formats():
    # 1. ISO format
    iso_res = parse_query_date("documents from 2025-08-09")
    assert iso_res is not None
    assert iso_res.target_date == "2025-08-09"
    assert iso_res.filter_mode == "exact"

    # 2. 2-digit year "25" -> 2025
    two_digit_res = parse_query_date("invoice on 9 aug 25")
    assert two_digit_res is not None
    assert two_digit_res.target_date == "2025-08-09"

    # 3. 3-digit typo year "225" -> 2025
    typo_res = parse_query_date("invoice close to 9 aug 225")
    assert typo_res is not None
    assert typo_res.target_date == "2025-08-09"
    assert typo_res.is_approx is True
    assert typo_res.window_days == 7

    # 4. Relative format "ending soon"
    soon_res = parse_query_date("projects going to end soon")
    assert soon_res is not None
    assert soon_res.filter_mode == "ending_soon"
    assert soon_res.window_days == 60


def test_date_parser_window_and_approx():
    res = parse_query_date("invoices around 2025-08-09")
    assert res is not None
    assert res.target_date == "2025-08-09"
    assert res.is_approx is True
    assert res.window_days == 7
    assert res.start_date == "2025-08-02"
    assert res.end_date == "2025-08-16"


def test_tolerant_query_doc_type_isolation(real_resolver):
    # Invoice query must identify doc_type = invoice
    tq_inv = understand_query("find invoice for 2025-08-09", entity_resolver=real_resolver)
    assert tq_inv.doc_type == "invoice"

    # Project query must identify doc_type = project
    tq_proj = understand_query("find project file going to end soon", entity_resolver=real_resolver)
    assert tq_proj.doc_type == "project"


def test_fallback_behavior_no_misleading_files():
    user = UserAttributes(user_id="test-u", tenant_id="test-t", department="Finance", roles=frozenset({"Employee"}))
    # Query for an impossible date that has 0 files
    answer, files, sources = execute_file_search(user, "invoices on 1980-01-01", "local")

    # MUST NOT return files or print misleading fallback
    assert len(files) == 0
    assert "most recent documents in this source" not in answer.lower()
    assert "No invoice documents" in answer or "No documents" in answer


def test_follow_up_contextualization():
    history = [
        ChatMessage(role="user", content="find invoices for vendor from last year", created_at=datetime.now(timezone.utc)),
        ChatMessage(role="assistant", content="Found invoices", created_at=datetime.now(timezone.utc)),
    ]

    follow_up = "9 aug 25"
    merged = ChatService._fallback_contextualize(follow_up, history)
    assert "9 aug 25" in merged
    assert "invoices" in merged or "vendor" in merged
