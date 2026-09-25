import base64
import json
import time
from datetime import datetime, timezone

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from backend.agents.security_gateway import SecureToolGateway, ToolContext, ToolPolicyDenied
from backend.security.audit import AuditLogger, InMemoryAuditSink
from backend.security.authorization import AuthorizationService, Permission, Resource, UserAttributes
from backend.security.authorization.rbac import Role
from backend.security.ai.network import SSRFProtection, URLValidationError
from backend.security.ai.output_guard import SensitiveDataFilter
from backend.security.token_validator import TokenValidator
from backend.integrations.email import EmailProviderContext, EmailSearchRequest, EmailService
from backend.integrations.email.service import ProviderEmailRepository
from backend.integrations.email.exceptions import EmailAccessDenied
from backend.retrieval.authorization import RetrievalAuthorizer
from backend.retrieval.models import AccessControlMetadata, KnowledgeChunk, SourceMetadata
from backend.sources.service import SourceReferenceService
from backend.sources.store import InMemorySourceReferenceStore


def _user(role=Role.EMPLOYEE, user_id="u1", tenant="t1", department="Projects"):
    return UserAttributes(user_id, tenant, department, frozenset({role}))


def _keys():
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public = private.public_key().public_numbers()
    def b64(n):
        raw = n.to_bytes((n.bit_length()+7)//8, "big")
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()
    jwk = {"kty":"RSA", "use":"sig", "alg":"RS256", "kid":"k1", "n":b64(public.n), "e":b64(public.e)}
    return private, jwk


def _validator(monkeypatch, issuer="https://issuer.example", audience="nanvi"):
    private, jwk = _keys()
    class Resp:
        def raise_for_status(self): pass
        def json(self): return {"keys":[jwk]}
    monkeypatch.setattr(httpx, "get", lambda *a, **k: Resp())
    return TokenValidator("https://issuer.example/.well-known/jwks.json", issuer, audience), private


def _token(private, **overrides):
    claims = {"sub":"u1","iss":"https://issuer.example","aud":"nanvi","iat":int(time.time()),"exp":int(time.time())+300,"tid":"t1","roles":["Employee"],"department":"Projects"}
    claims.update(overrides)
    return jwt.encode(claims, private, algorithm="RS256", headers={"kid":"k1"})


def test_auth_wrong_issuer_audience_expired_and_manipulated(monkeypatch):
    validator, private = _validator(monkeypatch)
    for token in (
        _token(private, iss="https://evil.example"),
        _token(private, aud="other-app"),
        _token(private, exp=int(time.time())-1),
        _token(private, roles=["CEO"]).rsplit(".", 1)[0] + ".invalid",
    ):
        with pytest.raises(Exception):
            validator.validate(token)


def test_auth_invalid_signature(monkeypatch):
    validator, private = _validator(monkeypatch)
    other, _ = _keys()
    token = _token(other)
    with pytest.raises(Exception):
        validator.validate(token)


def test_role_claim_cannot_escalate_without_valid_signature(monkeypatch):
    validator, private = _validator(monkeypatch)
    token = _token(private, roles=["CEO"])
    assert Role.CEO in validator.validate(token).roles
    forged = token.rsplit('.', 1)[0] + ".invalid"
    with pytest.raises(Exception):
        validator.validate(forged)


def test_rbac_vertical_and_horizontal_boundaries():
    auth = AuthorizationService()
    finance = Resource("f1", "company_file", "t1", department="Finance", attributes={"restricted_department":"Finance"})
    hr = Resource("h1", "company_file", "t1", department="HR", attributes={"restricted_department":"HR"})
    assert not auth.authorize(_user(), Permission.FINANCE_READ, finance).allowed
    assert not auth.authorize(_user(), Permission.HR_READ, hr).allowed
    assert not auth.authorize(_user(Role.FINANCE, department="Finance"), Permission.HR_READ, hr).allowed
    assert not auth.authorize(_user(Role.EMPLOYEE, user_id="u2"), Permission.FILE_READ, Resource("u1file","user_file","t1",owner_id="u1")).allowed
    assert not auth.authorize(_user(Role.EMPLOYEE, tenant="t2"), Permission.FILE_READ, Resource("x","company_file","t1")).allowed


def test_direct_tool_invocation_and_wrong_permission_denied():
    sink=InMemoryAuditSink(); gw=SecureToolGateway(AuthorizationService(), AuditLogger(sink))
    called=[]; resource=Resource("db","database_source","t1")
    with pytest.raises(ToolPolicyDenied):
        gw.execute(ToolContext("r", _user()), "database", Permission.DATABASE_WRITE, resource, lambda: called.append(1))
    assert not called


def test_tool_gateway_budget_is_request_scoped():
    sink=InMemoryAuditSink(); gw=SecureToolGateway(AuthorizationService(), AuditLogger(sink), max_tool_calls=1)
    resource=Resource("db","database_source","t1")
    c1=ToolContext("r1", _user()); c2=ToolContext("r2", _user(user_id="u2"))
    assert gw.execute(c1,"database",Permission.DATABASE_READ,resource,lambda:"ok") == "ok"
    with pytest.raises(ToolPolicyDenied):
        gw.execute(c1,"database",Permission.DATABASE_READ,resource,lambda:"bad")
    assert gw.execute(c2,"database",Permission.DATABASE_READ,resource,lambda:"ok") == "ok"


def test_structured_tool_output_is_filtered():
    sink=InMemoryAuditSink(); gw=SecureToolGateway(AuthorizationService(), AuditLogger(sink))
    resource=Resource("db","database_source","t1")
    out=gw.execute(ToolContext("r", _user()),"database",Permission.DATABASE_READ,resource,lambda:{"token":"api_key=SECRET123","nested":["C:\\CompanyData\\secret.txt"]})
    assert out["token"] == "[REDACTED]"
    assert out["nested"][0] == "[REDACTED]"


def test_email_context_must_match_principal_and_scope():
    class Provider:
        def search(self,*a): raise AssertionError("provider must not be called")
    svc=EmailService(ProviderEmailRepository(Provider()), AuthorizationService(), AuditLogger(InMemoryAuditSink()))
    with pytest.raises(EmailAccessDenied):
        svc.search(_user(), EmailProviderContext("u1","t1","tok",frozenset()), EmailSearchRequest(query="x"))
    with pytest.raises(EmailAccessDenied):
        svc.search(_user(), EmailProviderContext("u2","t1","tok",frozenset({"Mail.Read"})), EmailSearchRequest(query="x"))


def test_retrieval_uses_source_specific_permission():
    auth=AuthorizationService()
    authorizer=RetrievalAuthorizer(auth)
    email_chunk=KnowledgeChunk("c","email",SourceMetadata("email","m1",None,None,access=AccessControlMetadata("t1",owner_id="u1",resource_type="email_mailbox")),0)
    assert not authorizer.allowed(_user(tenant="t2"), email_chunk)


def test_source_lineage_requires_explicit_tenant():
    svc=SourceReferenceService(AuthorizationService(), AuditLogger(InMemoryAuditSink()), InMemorySourceReferenceStore())
    from backend.analysis.models import DataLineage
    # Missing lineage tenant must not inherit caller tenant and silently authorize.
    assert svc.from_lineage(_user(), "r", (DataLineage("file","x","x",(),tenant_id=""),)) == ()


def test_source_reference_cross_tenant_denied():
    svc=SourceReferenceService(AuthorizationService(), AuditLogger(InMemoryAuditSink()), InMemorySourceReferenceStore())
    from backend.analysis.models import DataLineage
    refs=svc.from_lineage(_user(),"r",(DataLineage("file","x","x",(),tenant_id="t1"),))
    with pytest.raises(Exception): svc.resolve_for_user(_user(tenant="t2"),"r",refs[0].reference_id)


def test_ssrf_blocks_local_and_non_https():
    guard=SSRFProtection(resolver=lambda *a,**k:[(None,None,None,None,("127.0.0.1",0))])
    with pytest.raises(URLValidationError): guard.validate("https://localhost/")
    with pytest.raises(URLValidationError): guard.validate("http://example.com/")
    with pytest.raises(URLValidationError): guard.validate("https://user:pass@example.com/")


def test_chat_request_is_authenticated():
    client=TestClient(__import__('backend.main',fromlist=['app']).app)
    r=client.post('/api/chat',json={'query':'hello'})
    assert r.status_code == 401


def test_malformed_json_is_rejected():
    client=TestClient(__import__('backend.main',fromlist=['app']).app)
    r=client.post('/api/chat',content='{"query":')
    assert r.status_code == 422

def test_conversation_history_is_tenant_scoped():
    from backend.chat.service import InMemoryConversationStore
    from backend.chat.models import ChatMessage
    store=InMemoryConversationStore()
    now=datetime.now(timezone.utc)
    store.bind_owner('c1','same-user','t1')
    store.append('c1',ChatMessage('user','tenant-one',now))
    assert store.list_for_user('same-user','t2') == ()
    assert len(store.list_for_user('same-user','t1')) == 1


def test_graph_message_id_is_path_encoded():
    request=httpx.Request('GET','https://graph.microsoft.com/v1.0/me/messages')
    response=httpx.Response(200,request=request,json={'id':'m/evil','conversationId':None,'subject':'x','from':None,'toRecipients':[],'ccRecipients':[],'receivedDateTime':None,'sentDateTime':None,'bodyPreview':'x','hasAttachments':False})
    class Client:
        def __init__(self): self.url=None
        def get(self,url,params=None,headers=None): self.url=url; return response
    from backend.integrations.email.graph import MicrosoftGraphEmailProvider
    client=Client(); provider=MicrosoftGraphEmailProvider(http_client=client)
    from backend.integrations.email.models import EmailProviderContext
    provider.get_message(EmailProviderContext('u1','t1','tok',frozenset({'Mail.Read'})),'m/evil')
    assert client.url.endswith('/m%2Fevil')
