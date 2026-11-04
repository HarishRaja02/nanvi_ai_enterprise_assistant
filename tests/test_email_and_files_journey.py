"""Tests for immediate recent emails and smooth file search with non-blocking follow-ups."""
from backend.security.authorization.rbac import Role
from backend.security.authorization.abac import UserAttributes
from backend.bootstrap import create_chat_service
from backend.chat.models import ChatRequest


def test_recent_email_and_refinement():
    user = UserAttributes(
        user_id="test-user-01",
        tenant_id="test-tenant",
        department="Engineering",
        roles=frozenset({Role.ADMIN}),
    )
    service = create_chat_service()

    # Step 1: User asks "recent email"
    # Must immediately return top 5 recent emails, NOT asking "Which source would you like me to search?"
    r1 = service.ask(user, ChatRequest(query="recent email", conversation_id="conv-email-flow"))
    assert "Which source would you like me to search?" not in r1.answer
    assert "most recent email" in r1.answer.lower()
    assert "| Subject | From | Date |" in r1.answer
    assert "put a sender name" in r1.answer.lower()

    # Step 2: User responds to the prompt with a sender name: "emails from David"
    r2 = service.ask(user, ChatRequest(query="emails from David", conversation_id="conv-email-flow"))
    assert "Which source would you like me to search?" not in r2.answer
    assert "david" in r2.answer.lower()
    assert "| Subject | From | Date |" in r2.answer


def test_chennai_files_and_date_refinement():
    user = UserAttributes(
        user_id="test-user-01",
        tenant_id="test-tenant",
        department="Engineering",
        roles=frozenset({Role.ADMIN}),
    )
    service = create_chat_service()

    # Step 1: User asks "check chennai realted files?"
    # Immediately searches primary storage (Local Storage) without asking repetitive questions
    r1 = service.ask(user, ChatRequest(query="check chennai realted files?", conversation_id="conv-chennai-flow"))
    assert "Which source would you like me to search?" not in r1.answer
    assert "Local Storage" in r1.answer
    assert "| File Name | File Path | Action |" in r1.answer

    # Step 2: User provides timeframe: "files modified on Oct 5"
    # Must filter the files for that date without asking "Which source would you like me to search?"
    r2 = service.ask(user, ChatRequest(query="files modified on Oct 5", conversation_id="conv-chennai-flow"))
    assert "Which source would you like me to search?" not in r2.answer
    assert "| File Name | File Path | Action |" in r2.answer
