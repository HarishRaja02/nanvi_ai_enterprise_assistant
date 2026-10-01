from __future__ import annotations

import pytest

from backend.agents.models import AgentRequest, Capability, OrchestrationState
from backend.agents.orchestrator import EnterpriseOrchestrator
from backend.chat.models import ChatRequest
from backend.chat.service import ChatService, InMemoryConversationStore, DeterministicTestAnswerer
from backend.llm.answerer import LLMChatAnswerer
from backend.llm.provider import BaseLLMProvider, LLMProviderError
from backend.security.authorization import UserAttributes
from backend.security.authorization.rbac import Role


@pytest.fixture
def test_user() -> UserAttributes:
    return UserAttributes("u-runtime", "tenant-runtime", "Projects", frozenset({Role.EMPLOYEE}))


class MockLLM(BaseLLMProvider):
    def __init__(self, response_text: str = "Mocked LLM answer"):
        super().__init__("mock-model")
        self.response_text = response_text
        self.received_messages = []

    def _call_api(self, messages: list[dict[str, str]]) -> str:
        self.received_messages.append(messages)
        return self.response_text


class FailingLLM(BaseLLMProvider):
    def __init__(self, error_message: str = "Simulated API error"):
        super().__init__("failing-model")
        self.error_message = error_message

    def _call_api(self, messages: list[dict[str, str]]) -> str:
        raise LLMProviderError(self.error_message)


def test_enterprise_orchestrator_returns_orchestration_state_from_langgraph(test_user: UserAttributes):
    orchestrator = EnterpriseOrchestrator()
    request = AgentRequest("req-1", test_user, "find project atlas")
    result = orchestrator.invoke(request)

    assert isinstance(result, OrchestrationState)
    assert result.request_id == "req-1"
    assert result.user_id == test_user.user_id
    assert result.tenant_id == test_user.tenant_id
    assert result.capability == Capability.KNOWLEDGE
    assert len(result.trace) >= 2
    assert "route:knowledge" in result.trace
    assert "agent:knowledge" in result.trace
    assert result.response is not None


def test_chat_service_with_deterministic_answerer(test_user: UserAttributes):
    orchestrator = EnterpriseOrchestrator()
    answerer = DeterministicTestAnswerer()
    store = InMemoryConversationStore()
    service = ChatService(orchestrator, answerer, store)

    response = service.ask(test_user, ChatRequest("What is project atlas?"))
    assert response.conversation_id
    assert response.capability == "knowledge"
    assert response.answer
    assert len(response.history) == 2
    assert response.history[0].role == "user"
    assert response.history[1].role == "assistant"


def test_chat_service_with_llm_answerer_success(test_user: UserAttributes):
    mock_llm = MockLLM("Here is the project atlas details from connected sources.")
    answerer = LLMChatAnswerer(mock_llm)
    orchestrator = EnterpriseOrchestrator()
    store = InMemoryConversationStore()
    service = ChatService(orchestrator, answerer, store)

    response = service.ask(test_user, ChatRequest("Tell me about project atlas"))
    assert response.answer == "Here is the project atlas details from connected sources."
    assert len(mock_llm.received_messages) == 1
    assert len(response.history) == 2


def test_chat_service_with_llm_answerer_handles_error(test_user: UserAttributes):
    failing_llm = FailingLLM("AI service authentication failed")
    answerer = LLMChatAnswerer(failing_llm)
    orchestrator = EnterpriseOrchestrator()
    store = InMemoryConversationStore()
    service = ChatService(orchestrator, answerer, store)

    response = service.ask(test_user, ChatRequest("Tell me about project atlas"))
    assert "unable to process your request" in response.answer
    assert "AI service authentication failed" in response.answer
    assert len(response.history) == 2


def test_conversation_summary_has_meaningful_title(test_user: UserAttributes):
    mock_llm = MockLLM("Here are the gold prices.")
    answerer = LLMChatAnswerer(mock_llm)
    orchestrator = EnterpriseOrchestrator()
    store = InMemoryConversationStore()
    service = ChatService(orchestrator, answerer, store)

    service.ask(test_user, ChatRequest("gold price today in chennai"))
    history = service.history(test_user)
    assert len(history) == 1
    assert history[0].title == "Gold Price Today in Chennai"


def test_chat_conversational_memory_isolation_and_contextualization(test_user: UserAttributes):
    mock_llm = MockLLM("Mocked response")
    answerer = LLMChatAnswerer(mock_llm)
    orchestrator = EnterpriseOrchestrator()
    store = InMemoryConversationStore()
    service = ChatService(orchestrator, answerer, store)

    # Chat 1 - Turn 1
    r1 = service.ask(test_user, ChatRequest("Hi"))
    c1 = r1.conversation_id
    assert c1

    # Chat 1 - Turn 2
    r2 = service.ask(test_user, ChatRequest("What is the weather today?", conversation_id=c1))
    assert r2.conversation_id == c1

    # Chat 1 - Turn 3
    r3 = service.ask(test_user, ChatRequest("What was my first question?", conversation_id=c1))
    assert r3.conversation_id == c1
    assert len(store.get(c1)) == 6

    # Verify history messages were passed in the payload
    last_call = mock_llm.received_messages[-1]
    # Check that previous turns are present in the call messages or prompt
    call_roles = [m["role"] for m in last_call]
    assert "user" in call_roles
    assert any("Hi" in m["content"] for m in last_call)

    # Chat 2 - Fresh conversation (isolation check)
    r_fresh = service.ask(test_user, ChatRequest("What was my first question?"))
    c2 = r_fresh.conversation_id
    assert c2 != c1
    assert len(store.get(c2)) == 2
    # Verify Chat 2's payload contains none of Chat 1's history
    fresh_call = mock_llm.received_messages[-1]
    assert not any("weather" in m["content"].lower() for m in fresh_call)

    # Pronoun resolution check
    r_rag1 = service.ask(test_user, ChatRequest("What is RAG?"))
    c3 = r_rag1.conversation_id
    assert c3 != c1 and c3 != c2

    contextualized = mock_llm.contextualize_query("Why is it useful?", store.get(c3))
    assert "RAG" in contextualized
    assert "it" not in contextualized.lower().split()
