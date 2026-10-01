from datetime import datetime, timezone
import httpx
import pytest

from backend.integrations.email import (
    EmailProviderContext, EmailSearchRequest, EmailService, EmailTool,
    MicrosoftGraphEmailProvider,
)
from backend.integrations.email.service import ProviderEmailRepository
from backend.integrations.email.exceptions import EmailAccessDenied
from backend.security.audit import AuditLogger, InMemoryAuditSink
from backend.security.authorization import AuthorizationService, Permission, Resource, UserAttributes


USER = UserAttributes(user_id="u1", tenant_id="t1", department="Projects", roles=frozenset({"Employee"}))
CTX = EmailProviderContext(user_id="u1", tenant_id="t1", access_token="delegated-test-token", granted_scopes=frozenset({"Mail.Read"}))


class FakeProvider:
    def __init__(self):
        self.calls = []
    def search(self, context, request):
        self.calls.append(("search", context, request))
        return []
    def get_thread(self, context, conversation_id):
        self.calls.append(("thread", context, conversation_id))
        from backend.integrations.email.models import EmailThread
        return EmailThread(conversation_id, ())
    def get_message(self, context, message_id):
        self.calls.append(("message", context, message_id))
        from backend.integrations.email.models import EmailMessage
        return EmailMessage(message_id, None, "Subject", None, (), (), None, None, None, False)


def make_service(provider=None):
    sink = InMemoryAuditSink()
    service = EmailService(ProviderEmailRepository(provider or FakeProvider()), AuthorizationService(), AuditLogger(sink))
    return service, sink


def test_authorization_happens_before_provider():
    provider = FakeProvider()
    service, sink = make_service(provider)
    denied = UserAttributes(user_id="u2", tenant_id="t1", department="Projects", roles=frozenset())
    with pytest.raises(EmailAccessDenied):
        service.search(denied, CTX, EmailSearchRequest(query="invoice"))
    assert provider.calls == []
    assert sink.events[-1].outcome == "deny"


def test_email_tool_does_not_need_graph_credentials():
    provider = FakeProvider()
    service, _ = make_service(provider)
    tool = EmailTool(service)
    result = tool.search(USER, CTX, EmailSearchRequest(sender="boss@example.com", after=datetime(2026,1,1,tzinfo=timezone.utc)))
    assert result == []
    assert provider.calls[0][1].access_token == "delegated-test-token"
    assert not hasattr(tool, "client_secret")
    assert not hasattr(tool, "refresh_token")


def test_graph_search_maps_metadata_and_date_filter():
    request = httpx.Request("GET", "https://graph.microsoft.com/v1.0/me/messages")
    response = httpx.Response(200, request=request, json={"value": [{
        "id": "m1", "conversationId": "c1", "subject": "Invoice", "from": {"emailAddress": {"name": "Boss", "address": "boss@example.com"}},
        "toRecipients": [{"emailAddress": {"address": "me@example.com"}}], "ccRecipients": [],
        "receivedDateTime": "2026-09-01T10:00:00Z", "sentDateTime": "2026-09-01T09:59:00Z",
        "bodyPreview": "Invoice attached", "hasAttachments": True, "webLink": "https://outlook.office.com/"
    }]})
    class Client:
        def __init__(self): self.last = None
        def get(self, url, params=None, headers=None): self.last = (url, params, headers); return response
    client = Client()
    provider = MicrosoftGraphEmailProvider(http_client=client)
    result = provider.search(CTX, EmailSearchRequest(sender="boss@example.com", after=datetime(2026,1,1,tzinfo=timezone.utc), max_results=10))
    assert result[0].subject == "Invoice"
    assert result[0].sender.address == "boss@example.com"
    assert "receivedDateTime ge" in client.last[1]["$filter"]
    assert client.last[2]["Authorization"] == "Bearer delegated-test-token"


def test_graph_search_escapes_filter_value():
    request = httpx.Request("GET", "https://graph.microsoft.com/v1.0/me/messages")
    response = httpx.Response(200, request=request, json={"value": []})
    class Client:
        def __init__(self): self.params = None
        def get(self, url, params=None, headers=None): self.params = params; return response
    client = Client()
    MicrosoftGraphEmailProvider(http_client=client).search(CTX, EmailSearchRequest(sender="a'b@example.com"))
    assert "a''b@example.com" in client.params["$filter"]


def test_graph_rejects_invalid_limit():
    with pytest.raises(ValueError):
        MicrosoftGraphEmailProvider(http_client=object()).search(CTX, EmailSearchRequest(max_results=101))


def test_thread_retrieval():
    request = httpx.Request("GET", "https://graph.microsoft.com/v1.0/me/messages")
    response = httpx.Response(200, request=request, json={"value": [{"id": "m1", "conversationId": "c1", "subject": "Hello", "from": None, "toRecipients": [], "ccRecipients": [], "receivedDateTime": None, "sentDateTime": None, "bodyPreview": "Hi", "hasAttachments": False}]})
    class Client:
        def get(self, *args, **kwargs): return response
    thread = MicrosoftGraphEmailProvider(http_client=Client()).get_thread(CTX, "c1")
    assert thread.conversation_id == "c1"
    assert thread.messages[0].id == "m1"
