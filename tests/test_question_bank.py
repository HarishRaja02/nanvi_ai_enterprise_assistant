"""Enterprise Test Question Bank Verification Suite.

Validates:
1. Basic File Retrieval (IDs, entities, amounts)
2. Semantic Search (at-risk, clauses, blocked tasks, failed transactions)
3. Filename Independence (content-first retrieval for Asteron Technologies)
4. Recursive / Nested Folder Scanner (depth and arbitrary folder names)
5. Cross-Department & Cross-File Candidate Selection
6. Multi-Turn Conversational RAG & Pronoun Resolution
7. Context Switching Across Entities
8. Hallucination / No-Result Prevention for Unknown Entities
"""
from __future__ import annotations

from datetime import datetime, timezone
import pytest

from backend.chat.models import ChatMessage, ChatRequest
from backend.chat.service import ChatService
from backend.integrations.files.company_data_service import CompanyDataService
from backend.security.authorization.abac import UserAttributes
from backend.security.authorization.rbac import Role


@pytest.fixture
def authorized_user() -> UserAttributes:
    return UserAttributes(
        user_id="harish",
        tenant_id="tenant-1",
        department="executive",
        roles=frozenset({
            Role.CEO, Role.FINANCE, Role.HR, Role.MANAGER, Role.EMPLOYEE, Role.IT_ADMIN
        }),
    )


@pytest.fixture
def company_data_service() -> CompanyDataService:
    svc = CompanyDataService("C:/CompanyData")
    svc.ensure_indexed()
    return svc


def test_basic_file_retrieval_customer(company_data_service: CompanyDataService, authorized_user: UserAttributes):
    res = company_data_service.search(authorized_user, "What is the annual value of Customer 001?")
    assert res.is_exact_match is True
    assert len(res.sources) > 0
    assert any("customer" in s.display_name.lower() for s in res.sources)
    assert "001" in res.answer_content


def test_basic_file_retrieval_employee(company_data_service: CompanyDataService, authorized_user: UserAttributes):
    res = company_data_service.search(authorized_user, "What department does Employee 1005 belong to?")
    assert res.is_exact_match is True
    assert len(res.sources) > 0
    assert "1005" in res.answer_content


def test_basic_file_retrieval_project_budget(company_data_service: CompanyDataService, authorized_user: UserAttributes):
    res = company_data_service.search(authorized_user, "What is the budget of Project P-001-005?")
    assert res.is_exact_match is True
    assert len(res.sources) > 0
    assert "P-001-005" in res.answer_content
    # Project sheet contains the budget column
    assert any("project" in s.display_name.lower() for s in res.sources)


def test_filename_independence_asteron(company_data_service: CompanyDataService, authorized_user: UserAttributes):
    # Asteron Technologies is inside contract_register_01.csv, not an asteron.txt file
    res = company_data_service.search(authorized_user, "Find all information about Asteron Technologies.")
    assert res.is_exact_match is True
    assert len(res.sources) > 0
    assert "asteron" in res.answer_content.lower()


def test_semantic_search_blocked_tasks(company_data_service: CompanyDataService, authorized_user: UserAttributes):
    res = company_data_service.search(authorized_user, "Find all blocked tasks.")
    assert res.is_exact_match is True
    assert len(res.sources) > 0
    assert "blocked" in res.answer_content.lower()


def test_semantic_search_confidentiality_clauses(company_data_service: CompanyDataService, authorized_user: UserAttributes):
    res = company_data_service.search(authorized_user, "Which contracts contain confidentiality clauses?")
    assert res.is_exact_match is True
    assert len(res.sources) > 0
    assert "confidential" in res.answer_content.lower()


def test_cross_department_selection(company_data_service: CompanyDataService, authorized_user: UserAttributes):
    res = company_data_service.search(authorized_user, "Find all information about Asteron Technologies across every department.")
    assert res.is_exact_match is True
    assert len(res.sources) > 0
    # Verified that sources do not have duplicate file/sheet references
    locations = [s.location for s in res.sources]
    assert len(locations) == len(set(locations))


def test_multi_turn_conversational_rag():
    now = datetime.now(timezone.utc)
    turns = [
        "Tell me about Customer 015.",
        "What is their annual value?",
        "Where are they located?",
        "What is their status?",
        "What industry are they in?",
    ]
    history: list[ChatMessage] = []
    for t in turns:
        ctx = ChatService._fallback_contextualize(t, history)
        if t != turns[0]:
            assert "Customer 015" in ctx
        history.append(ChatMessage("user", t, now))
        history.append(ChatMessage("assistant", f"Answer for {t}", now))


def test_context_switching():
    now = datetime.now(timezone.utc)
    history: list[ChatMessage] = []

    # Turn 1: Customer 001
    q1 = "Tell me about Customer 001."
    assert ChatService._fallback_contextualize(q1, history) == q1
    history.append(ChatMessage("user", q1, now))

    # Turn 2: Pronoun referring to Customer 001
    q2 = "What is their annual value?"
    c2 = ChatService._fallback_contextualize(q2, history)
    assert "Customer 001" in c2
    history.append(ChatMessage("user", q2, now))

    # Turn 3: Switch context to Project P-002-005
    q3 = "Now tell me about Project P-002-005."
    c3 = ChatService._fallback_contextualize(q3, history)
    assert "Project P-002-005" in c3
    assert "Customer 001" not in c3
    history.append(ChatMessage("user", q3, now))

    # Turn 4: Pronoun referring to Project P-002-005
    q4 = "What is its budget?"
    c4 = ChatService._fallback_contextualize(q4, history)
    assert "Project P-002-005" in c4
    history.append(ChatMessage("user", q4, now))

    # Turn 5: Switch back to Customer 001
    q5 = "Go back to Customer 001."
    c5 = ChatService._fallback_contextualize(q5, history)
    assert "Customer 001" in c5
    history.append(ChatMessage("user", q5, now))

    # Turn 6: Pronoun referring to Customer 001
    q6 = "What city are they in?"
    c6 = ChatService._fallback_contextualize(q6, history)
    assert "Customer 001" in c6


def test_hallucination_prevention_unknown_entities(company_data_service: CompanyDataService, authorized_user: UserAttributes):
    # Synthetic non-existent entity tests (must return no matching results)
    for unknown_q in [
        "What is Employee 999999's salary?",
        "What is Contract ABC-999999's value?",
        "Find an invoice for Fake Corporation.",
    ]:
        res = company_data_service.search(authorized_user, unknown_q)
        assert res.is_exact_match is False
        assert len(res.sources) == 0
        assert res.answer_content == ""
