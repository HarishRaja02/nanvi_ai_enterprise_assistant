from backend.retrieval import *
from backend.security.audit import AuditLogger, InMemoryAuditSink
from backend.security.authorization import AuthorizationService, UserAttributes


def source(source_id, restricted=None, tenant="t1", department=None):
    return SourceMetadata(
        source_type="pdf", source_id=source_id, filename=source_id.split("/")[-1], path=source_id,
        page=3, modified_at=None,
        access=AccessControlMetadata(tenant_id=tenant, department=department, restricted_department=restricted),
    )


class FakeEmbedding(EmbeddingProvider):
    def embed(self, text):
        t = text.lower()
        return [float("project" in t), float("salary" in t), float("customer" in t)]


class CaptureReranker(Reranker):
    def rerank(self, query, hits, top_k):
        return hits[:top_k]


def build():
    sink = InMemoryAuditSink()
    service = KnowledgeRetrievalService(
        FakeEmbedding(), InMemoryVectorStore(), KeywordRetriever(), CaptureReranker(),
        AuthorizationService(), AuditLogger(sink), DocumentChunker(max_chars=200, overlap=20)
    )
    return service, sink


def test_chunking_retains_source_metadata():
    service, _ = build()
    chunks = service.index("Project roadmap and milestones.\n\nMore details about delivery.", source("Projects/roadmap.pdf"))
    assert chunks
    assert chunks[0].source.source_type == "pdf"
    assert chunks[0].source.source_id == "Projects/roadmap.pdf"
    assert chunks[0].source.filename == "roadmap.pdf"
    assert chunks[0].source.path == "Projects/roadmap.pdf"
    assert chunks[0].source.page == 3


def test_keyword_retrieval():
    service, _ = build()
    service.index("Project Alpha has a delivery milestone.", source("Projects/a.pdf"))
    service.index("Customer renewal information.", source("Customers/c.pdf"))
    user = UserAttributes("u1", "t1", "Projects", frozenset({"Employee"}))
    result = service.retrieve(user, RetrievalRequest("project milestone", top_k=3))
    assert result.hits
    assert result.hits[0].chunk.source.filename == "a.pdf"


def test_hybrid_uses_vector_and_keyword():
    service, _ = build()
    service.index("Project delivery plan.", source("Projects/a.pdf"))
    result = service.retrieve(UserAttributes("u1", "t1", "Projects", frozenset({"Employee"})), RetrievalRequest("project", top_k=3))
    assert result.hits
    assert result.hits[0].retrieval_method == "hybrid"


def test_unauthorized_hr_content_never_returned():
    service, sink = build()
    service.index("Employee salary is confidential.", source("HR/salary.pdf", restricted="HR"))
    service.index("Project status is active.", source("Projects/status.pdf"))
    employee = UserAttributes("u1", "t1", "Projects", frozenset({"Employee"}))
    result = service.retrieve(employee, RetrievalRequest("salary confidential", top_k=5))
    assert all("salary" not in hit.chunk.content.lower() for hit in result.hits)
    assert sink.events[-1].event_type == "knowledge_retrieval"
    assert sink.events[-1].metadata["denied_candidates"] >= 1


def test_hr_user_can_receive_hr_content():
    service, _ = build()
    service.index("Employee salary is confidential.", source("HR/salary.pdf", restricted="HR"))
    hr = UserAttributes("u2", "t1", "HR", frozenset({"HR"}))
    result = service.retrieve(hr, RetrievalRequest("salary", top_k=3))
    assert result.hits[0].chunk.source.path == "HR/salary.pdf"


def test_cross_tenant_content_never_returned():
    service, _ = build()
    service.index("Project Alpha internal information.", source("Projects/a.pdf", tenant="tenant-A"))
    user = UserAttributes("u1", "tenant-B", "Projects", frozenset({"Employee"}))
    result = service.retrieve(user, RetrievalRequest("Project Alpha", top_k=5))
    assert result.hits == ()


def test_email_source_metadata():
    from backend.integrations.email.models import EmailMessage
    from backend.retrieval.ingestion import source_from_email
    msg = EmailMessage("m1", "c1", "Customer renewal", None, (), (), None, None, "renewal details", False)
    src = source_from_email(msg, "t1", "u1")
    assert src.source_type == "email"
    assert src.source_id == "m1"
    assert src.extra["conversation_id"] == "c1"
    assert src.access.owner_id == "u1"
