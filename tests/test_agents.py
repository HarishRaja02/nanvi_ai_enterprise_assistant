import pytest
from backend.agents.models import Capability, AgentRequest, OrchestrationState
from backend.agents.interfaces import RuleBasedRouter, LLMRouter
from backend.agents.security_gateway import SecureToolGateway, ToolContext, ToolPolicyDenied
from backend.security.audit import AuditLogger, InMemoryAuditSink
from backend.security.authorization import AuthorizationService, Permission, Resource, UserAttributes


def user(role="Employee"):
    return UserAttributes(user_id="u1", tenant_id="t1", department="Projects", roles=frozenset({role}))


def test_router_examples():
    r = RuleBasedRouter()
    assert r.route("Find Project XYZ documents") == Capability.KNOWLEDGE
    assert r.route("What did ABC ask in their emails?") == Capability.EMAIL
    assert r.route("Compare sales this month with last month") == Capability.DATA_ANALYSIS
    assert r.route("Show overdue invoices above $10,000") == Capability.DATABASE


def test_orchestration_state_has_no_secret_fields():
    state = OrchestrationState.from_request(AgentRequest("r1", user(), "find project"))
    fields = set(state.__dataclass_fields__)
    assert not {"password", "api_key", "access_token", "refresh_token", "client_secret", "database_password"} & fields


def test_secure_gateway_requires_authorization_before_execution():
    sink = InMemoryAuditSink()
    gateway = SecureToolGateway(AuthorizationService(), AuditLogger(sink))
    called = []
    resource = Resource("r1", "email_mailbox", "t1", owner_id="u1")
    with pytest.raises(ToolPolicyDenied):
        gateway.execute(ToolContext("req1", UserAttributes("u1", "t1", "Projects", frozenset())), "email", Permission.EMAIL_READ, resource, lambda: called.append(1))
    assert called == []
    assert sink.events[-1].outcome == "deny"


def test_secure_gateway_policy_runs_before_execution():
    sink = InMemoryAuditSink()
    gateway = SecureToolGateway(AuthorizationService(), AuditLogger(sink))
    called = []
    resource = Resource("r1", "email_mailbox", "t1", owner_id="u1")
    with pytest.raises(ToolPolicyDenied):
        gateway.execute(ToolContext("req1", user()), "email", Permission.EMAIL_READ, resource, lambda: called.append(1), policy=lambda: False)
    assert called == []
    assert sink.events[-1].metadata["reason"] == "Policy validation failed"


def test_secure_gateway_audits_success():
    sink = InMemoryAuditSink()
    gateway = SecureToolGateway(AuthorizationService(), AuditLogger(sink))
    resource = Resource("r1", "email_mailbox", "t1", owner_id="u1")
    result = gateway.execute(ToolContext("req1", user()), "email", Permission.EMAIL_READ, resource, lambda: "ok")
    assert result == "ok"
    assert sink.events[-1].outcome == "allow"
