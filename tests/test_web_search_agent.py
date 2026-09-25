import pytest
from backend.agents.models import Capability, AgentRequest
from backend.agents.interfaces import RuleBasedRouter
from backend.agents.capability_agents import WebSearchAgent, run_web_agent
from backend.agents.orchestrator import EnterpriseOrchestrator
from backend.agents.security_gateway import SecureToolGateway, ToolContext
from backend.security.audit import AuditLogger, InMemoryAuditSink
from backend.security.authorization import AuthorizationService, Permission, Resource, UserAttributes
from backend.integrations.web.service import WebSearchService, WebSearchResult
from services.web_search import search_web


def _make_user(role="Employee"):
    return UserAttributes(user_id="u1", tenant_id="t1", department="Engineering", roles=frozenset({role}))


def test_rule_based_router_routes_web_search():
    router = RuleBasedRouter()
    assert router.route("Search the web for AI developments") == Capability.WEB_SEARCH
    assert router.route("Search online for market news") == Capability.WEB_SEARCH
    assert router.route("Find external competitor data") == Capability.WEB_SEARCH


def test_web_search_service_to_source_references():
    service = WebSearchService(api_key="mock-key")
    results = [
        WebSearchResult(
            title="AI Regulation 2026",
            url="https://example.com/ai-regulation",
            content="European Union and global AI compliance standards updated in 2026.",
        )
    ]
    refs = service.to_source_references(results, "req-123")
    assert len(refs) == 1
    ref = refs[0]
    assert ref.source_type.value == "website"
    assert ref.display_name == "AI Regulation 2026"
    assert ref.href == "https://example.com/ai-regulation"
    assert ref.location == "https://example.com/ai-regulation"


def test_web_search_agent_gateway_execution():
    sink = InMemoryAuditSink()
    auth = AuthorizationService()
    gateway = SecureToolGateway(auth, AuditLogger(sink))

    class MockSearchService:
        is_configured = True
        def search(self, query, max_results=5):
            return [
                WebSearchResult(
                    title="Mock AI Report",
                    url="https://example.org/ai-news",
                    content="Breakthroughs in artificial intelligence technology.",
                )
            ]
        def to_source_references(self, results, request_id):
            service = WebSearchService(api_key="mock")
            return service.to_source_references(results, request_id)

    class MockLLM:
        def generate(self, prompt, system=None):
            return "Here is the synthesized web research about AI breakthroughs."

    agent = WebSearchAgent(
        web_search_service=MockSearchService(),
        gateway=gateway,
        llm_provider=MockLLM(),
    )

    request = AgentRequest(
        request_id="req-web-1",
        user=_make_user("Employee"),
        query="What are the latest AI breakthroughs?",
    )

    response = agent.run(request)
    assert response.capability == Capability.WEB_SEARCH
    assert "synthesized web research" in response.content
    assert len(response.sources) == 1
    assert response.sources[0].href == "https://example.org/ai-news"

    # Verify audit trail
    assert any(e.outcome == "allow" and e.resource_id == "web-search" for e in sink.events)


def test_orchestrator_routes_and_invokes_web_search():
    class MockSearchService:
        is_configured = True
        def search(self, query, max_results=5):
            return [
                WebSearchResult(
                    title="Live Web Results",
                    url="https://example.com/news",
                    content="Information from the web.",
                )
            ]
        def to_source_references(self, results, request_id):
            return WebSearchService(api_key="mock").to_source_references(results, request_id)

    web_agent = WebSearchAgent(
        web_search_service=MockSearchService(),
        llm_provider=type("LLM", (), {"generate": lambda self, p, system=None: "Synthesized web response."})(),
    )

    orchestrator = EnterpriseOrchestrator(
        agents={
            Capability.WEB_SEARCH: web_agent,
            Capability.KNOWLEDGE: web_agent,
            Capability.DATABASE: web_agent,
            Capability.EMAIL: web_agent,
            Capability.DATA_ANALYSIS: web_agent,
            Capability.REPORT: web_agent,
        }
    )

    req = AgentRequest("req-orch", _make_user("CEO"), "Search online for market intelligence")
    state = orchestrator.invoke(req, forced_capability=Capability.WEB_SEARCH)
    assert state.capability == Capability.WEB_SEARCH
    assert state.response is not None
    assert "Synthesized web response" in state.response.content
    assert len(state.response.sources) == 1


def test_live_tavily_search():
    # Tests live Tavily web search using the configured API key
    results = search_web("Latest AI technology announcements 2026", max_results=2)
    assert isinstance(results, list)
    if results:
        assert "title" in results[0]
        assert "url" in results[0]
        assert "content" in results[0]


def test_run_web_agent_function():
    # Test the standalone run_web_agent function
    answer = run_web_agent("What is Tavily?")
    assert isinstance(answer, str)
    assert len(answer) > 0


def test_chat_service_routes_web_search():
    from backend.bootstrap import create_chat_service
    from backend.chat.models import ChatRequest

    chat_service = create_chat_service()
    user = _make_user("Employee")
    resp = chat_service.ask(user, ChatRequest(query="Search the web for the latest artificial intelligence news"))
    assert "web_search" in resp.capability
    assert len(resp.sources) > 0
    assert any(s.source_type.value == "website" for s in resp.sources)
    assert resp.answer


def test_gold_price_query_routes_to_web_search():
    from backend.bootstrap import create_chat_service
    from backend.chat.models import ChatRequest

    chat_service = create_chat_service()
    user = _make_user("Employee")
    resp = chat_service.ask(user, ChatRequest(query="gold price today in chennai"))
    assert "web_search" in resp.capability
    assert len(resp.sources) > 0
    assert any(s.source_type.value == "website" for s in resp.sources)
    assert resp.answer
