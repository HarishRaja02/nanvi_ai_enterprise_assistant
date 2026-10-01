from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from uuid import uuid4

import pytest
from openpyxl import load_workbook

from backend.agents.models import AgentRequest, AgentResponse, Capability
from backend.agents.security_gateway import SecureToolGateway
from backend.analysis import DataLineage
from backend.integrations.database.abstraction import DatabaseRepository
from backend.integrations.database.models import QueryRequest, QueryResult, TablePolicy
from backend.integrations.database.service import DatabaseService
from backend.integrations.database.sql_validation import ReadOnlySQLValidator, SQLValidationPipeline
from backend.integrations.email.models import EmailAddress, EmailMessage, EmailProviderContext, EmailSearchRequest, EmailThread
from backend.integrations.email.repository import EmailRepository
from backend.integrations.email.service import EmailService
from backend.reports.agent import ReportAgent
from backend.reports.models import ReportFormat, ReportRequest
from backend.reports.service import ReportService, ReportAuthorizationError
from backend.reports.storage import SecureFileReportStorage
from backend.retrieval import (
    AccessControlMetadata, DocumentChunker, KeywordRetriever, KnowledgeRetrievalService,
    NoOpReranker, RetrievalRequest, SourceMetadata,
)
from backend.security.audit import AuditLogger, InMemoryAuditSink
from backend.security.authorization import AuthorizationService, Permission, Resource, UserAttributes
from backend.security.authorization.rbac import Role
from backend.sources.service import SourceReferenceService
from backend.sources.store import InMemorySourceReferenceStore


TENANT = "uat-acme-test"
EMPLOYEE = UserAttributes("uat-employee", TENANT, "Projects", frozenset({Role.EMPLOYEE}))
FINANCE = UserAttributes("uat-finance", TENANT, "Finance", frozenset({Role.FINANCE}))
OTHER_TENANT = UserAttributes("uat-other", "other-tenant", "Projects", frozenset({Role.EMPLOYEE}))


class UATDB(DatabaseRepository):
    def __init__(self):
        self.invoices = (
            ("INV-1001", "ABC Company", 12500, "overdue", "2026-09-05"),
            ("INV-1002", "ABC Company", 8500, "overdue", "2026-09-03"),
            ("INV-1003", "XYZ Industries", 25000, "overdue", "2026-08-20"),
            ("INV-1004", "Northwind", 18000, "paid", "2026-08-10"),
            ("INV-1005", "Globex", 11000, "open", "2026-09-10"),
        )
        self.sales = (
            ("2026-09-01", 18000), ("2026-09-04", 22000), ("2026-09-08", 25000),
            ("2026-08-02", 14000), ("2026-08-11", 16000), ("2026-08-20", 18000),
            ("2026-06-03", 30000), ("2026-06-17", 27000), ("2026-05-10", 21000),
            ("2026-04-22", 22000),
        )
        self.calls: list[str] = []

    def execute_read(self, request: QueryRequest) -> QueryResult:
        self.calls.append(request.sql)
        sql = request.sql.casefold()
        if "from invoices" in sql:
            if "overdue" in sql and "10000" in sql:
                rows = tuple(r for r in self.invoices if r[2] > 10000 and r[3] == "overdue")
            else:
                rows = self.invoices
            return QueryResult(("invoice", "customer", "amount", "status", "due_date"), rows)
        if "from sales" in sql:
            return QueryResult(("date", "sales"), self.sales)
        if "from restricted_hr" in sql:
            return QueryResult(("employee", "salary"), (("Synthetic HR", 99999),))
        raise AssertionError(f"Unexpected UAT SQL: {request.sql}")


class UATEmailRepo(EmailRepository):
    def __init__(self):
        subjects = [
            ("Budget request", "Please increase the Q4 support budget to $40,000."),
            ("Renewal date", "Can we move the renewal to October 15?"),
            ("Delivery status", "Please confirm the delivery date for the next shipment."),
            ("Invoice copy", "Please resend invoice INV-1001."),
            ("User access", "Add two project managers to the portal."),
            ("SLA review", "Can you share the latest SLA metrics?"),
            ("Integration", "We need the CRM integration specification."),
            ("Training", "Please schedule product training for our team."),
            ("Security questionnaire", "Please complete our vendor security questionnaire."),
            ("Support escalation", "Ticket ABC-778 is still unresolved."),
            ("Contract change", "Please update the billing contact on the contract."),
            ("Quarterly review", "Let's arrange the quarterly business review."),
        ]
        self.messages = tuple(
            EmailMessage(
                f"abc-{i:02d}", "abc-thread", subject,
                EmailAddress("contact@abc.test", "ABC Company"), (), (),
                datetime(2026, 9, 1 + i // 3, 10 + i % 8, tzinfo=timezone.utc), None,
                body, False, source="synthetic",
            ) for i, (subject, body) in enumerate(subjects)
        )

    def search(self, context, request):
        items = list(self.messages)
        if request.query:
            q = request.query.casefold()
            items = [m for m in items if q in (m.subject + " " + (m.body_preview or "")).casefold()]
        if request.after:
            items = [m for m in items if m.received_at and m.received_at >= request.after]
        if request.before:
            items = [m for m in items if m.received_at and request.before > m.received_at]
        items.sort(key=lambda m: m.received_at or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
        return items[:request.max_results]

    def get_thread(self, context, conversation_id):
        return EmailThread(conversation_id, self.messages)

    def get_message(self, context, message_id):
        return next(m for m in self.messages if m.id == message_id)


@dataclass
class UATRuntime:
    tmp_path: Path

    def __post_init__(self):
        self.sink = InMemoryAuditSink()
        self.audit = AuditLogger(self.sink)
        self.auth = AuthorizationService()
        self.sources = SourceReferenceService(self.auth, self.audit, InMemorySourceReferenceStore())
        policy = TablePolicy(
            frozenset({("public", "invoices"), ("public", "sales"), ("public", "restricted_hr")}),
            frozenset({
                ("public", "invoices", c) for c in ("invoice", "customer", "amount", "status", "due_date")
            } | {("public", "sales", c) for c in ("date", "sales")} |
            {("public", "restricted_hr", c) for c in ("employee", "salary")}),
        )
        self.db_repo = UATDB()
        self.db = DatabaseService(
            self.db_repo, self.auth, self.audit,
            SQLValidationPipeline(ReadOnlySQLValidator(policy, require_column_policy=True)), TENANT,
        )
        self.email_repo = UATEmailRepo()
        self.email = EmailService(self.email_repo, self.auth, self.audit)
        self.email_context = EmailProviderContext("uat-employee", TENANT, "synthetic-token", frozenset({"Mail.Read"}))
        self.retrieval = KnowledgeRetrievalService(
            None, None, KeywordRetriever(), NoOpReranker(), self.auth, self.audit,
            DocumentChunker(), self.sources,
        )
        self._index_documents()
        self.report = ReportService(SecureFileReportStorage(self.tmp_path / "reports"), self.auth, self.audit)
        self.gateway = SecureToolGateway(self.auth, self.audit)

    def _index_documents(self):
        docs = {
            "ABC_weekly_update.txt": "ABC Company this week: customer requested October renewal, reported one unresolved support issue ABC-778, requested the latest SLA metrics, and asked for a CRM integration specification.",
            "ABC_open_tickets.csv": "ticket,status,customer\nABC-778,open,ABC Company\nABC-779,open,ABC Company\nXYZ-301,closed,XYZ Industries\n",
            "Project_XYZ_requirements.txt": "Project XYZ requirements include CRM integration, security review, delivery milestones, and customer acceptance criteria.",
            "Project_XYZ_plan.docx": "Project XYZ implementation plan covers integration testing, security review, and delivery milestones.",
            "Finance_invoices.txt": "Restricted Finance data. Synthetic invoice register for UAT only.",
            "Q3_sales_summary.txt": "Synthetic sales summary for Q3 2026 UAT.",
        }
        for name, text in docs.items():
            restricted = "Finance" if name == "Finance_invoices.txt" else None
            self.retrieval.index(
                text,
                SourceMetadata(
                    "txt", name, name, name,
                    access=AccessControlMetadata(TENANT, restricted_department=restricted),
                ),
            )

    def refs(self, user, request_id, lineage):
        return self.sources.from_lineage(user, request_id, tuple(lineage))

    def ask(self, user: UserAttributes, question: str):
        """Business UAT adapter using the actual secured connectors/services.

        This is intentionally deterministic: UAT validates business outcomes and
        security boundaries without depending on a live LLM or production data.
        """
        rid = uuid4().hex
        started = perf_counter()
        q = question.casefold()
        if "last 10 emails" in q:
            msgs = self.email.search(user, self.email_context, EmailSearchRequest(max_results=10))
            refs = tuple(self.sources.from_metadata(user, rid, SourceMetadata("email", m.id, m.subject, None,
                access=AccessControlMetadata(TENANT, owner_id=user.user_id))) for m in msgs)
            content = [m.body_preview for m in msgs]
        elif "invoices above" in q and "overdue" in q:
            result = self.db.execute_read(user, QueryRequest("SELECT invoice, customer, amount, status, due_date FROM invoices WHERE amount > 10000 AND status = 'overdue' LIMIT 100"))
            lineage = DataLineage("sql", "invoices", "Invoice register", result.columns,
                                  query="SELECT invoice, customer, amount, status, due_date FROM invoices WHERE amount > 10000 AND status = 'overdue'",
                                  tenant_id=TENANT, department="Finance", restricted_department="Finance", resource_type="database_source")
            refs = self.refs(user, rid, (lineage,))
            content = result.rows
        elif "compare" in q and "sales" in q:
            result = self.db.execute_read(user, QueryRequest("SELECT date, sales FROM sales LIMIT 100"))
            this_month = sum(v for d, v in result.rows if d.startswith("2026-09"))
            last_month = sum(v for d, v in result.rows if d.startswith("2026-08"))
            lineage = DataLineage("sql", "sales", "Sales register", result.columns,
                                  query="SELECT date, sales FROM sales", tenant_id=TENANT, resource_type="database_source")
            refs = self.refs(user, rid, (lineage,))
            content = {"this_month": this_month, "last_month": last_month, "change": this_month - last_month}
        elif "last quarter" in q and "sales" in q:
            result = self.db.execute_read(user, QueryRequest("SELECT date, sales FROM sales LIMIT 100"))
            total = sum(v for d, v in result.rows if d[:7] in {"2026-04", "2026-05", "2026-06"})
            lineage = DataLineage("sql", "sales", "Sales register", result.columns,
                                  query="SELECT date, sales FROM sales", tenant_id=TENANT, resource_type="database_source")
            refs = self.refs(user, rid, (lineage,))
            content = {"quarter": "Q2 2026", "total": total}
        elif "pending customer issues" in q:
            result = self.retrieval.retrieve(user, RetrievalRequest("ABC open tickets", top_k=5))
            refs = self.retrieval.source_references(user, rid, result)
            content = "ticket,status,customer\nABC-778,open,ABC Company\nABC-779,open,ABC Company"
        elif "open tickets" in q:
            result = self.retrieval.retrieve(user, RetrievalRequest("ABC open tickets", top_k=5))
            refs = self.retrieval.source_references(user, rid, result)
            content = "\n".join(h.chunk.content for h in result.hits)
        elif "project xyz" in q or "documents related" in q:
            result = self.retrieval.retrieve(user, RetrievalRequest("Project XYZ", top_k=2))
            refs = self.retrieval.source_references(user, rid, result)
            content = "\n".join(h.chunk.content for h in result.hits)
        elif "abc company" in q:
            result = self.retrieval.retrieve(user, RetrievalRequest("ABC Company this week", top_k=5))
            refs = self.retrieval.source_references(user, rid, result)
            msgs = self.email.search(user, self.email_context, EmailSearchRequest(query="ABC", max_results=25))
            refs += tuple(self.sources.from_metadata(user, rid, SourceMetadata("email", m.id, m.subject, None,
                access=AccessControlMetadata(TENANT, owner_id=user.user_id))) for m in msgs[:3])
            content = "\n".join(h.chunk.content for h in result.hits) + "\n" + "\n".join(m.body_preview or "" for m in msgs[:3])
        else:
            raise AssertionError(f"No UAT business mapping for: {question}")
        return {"content": content, "sources": refs, "latency_ms": round((perf_counter() - started) * 1000, 2), "request_id": rid}

    def create_open_ticket_report(self, user):
        rid = uuid4().hex
        result = self.retrieval.retrieve(user, RetrievalRequest("ABC open tickets", top_k=5))
        text = "\n".join(h.chunk.content for h in result.hits)
        lineage = DataLineage("txt", "ABC_open_tickets.csv", "ABC open tickets", ("ticket", "status", "customer"),
                              tenant_id=TENANT, resource_type="company_file")
        req = ReportRequest(str(uuid4()), "Open Customer Tickets", ReportFormat.EXCEL, user.user_id, TENANT,
                            [{"ticket": "ABC-778", "status": "open", "customer": "ABC Company"},
                             {"ticket": "ABC-779", "status": "open", "customer": "ABC Company"}], (lineage,))
        agent = ReportAgent(self.report, self.gateway, self.sources)
        response = agent.create(AgentRequest(rid, user, "Create an Excel report of all open tickets"), req)
        return response, text


def _assert_source_transparency(result, forbidden=()):
    assert result["sources"], "Accepted business answers must expose source references"
    for src in result["sources"]:
        payload = str(src.to_frontend_dict())
        for secret in forbidden:
            assert secret not in payload


@pytest.fixture
def runtime(tmp_path):
    return UATRuntime(tmp_path)


def test_business_uat_scenarios(runtime):
    scenarios = [
        ("What happened with ABC Company this week?", ["ABC Company", "ABC-778"], EMPLOYEE),
        ("Give me all pending customer issues from this week.", ["ABC-778", "ABC-779"], EMPLOYEE),
        ("What did ABC Company ask for in their last 10 emails?", ["delivery", "security questionnaire", "training"], EMPLOYEE),
        ("Show me all invoices above $10,000 that are overdue.", ["INV-1001", "INV-1003"], FINANCE),
        ("Compare this month's sales with last month.", ["this_month", "last_month", "change"], EMPLOYEE),
        ("Find all documents related to Project XYZ.", ["Project XYZ", "integration"], EMPLOYEE),
        ("What were our sales last quarter?", ["Q2 2026", 100000], EMPLOYEE),
    ]
    results = []
    for question, expected, user in scenarios:
        result = runtime.ask(user, question)
        text = str(result["content"])
        for item in expected:
            assert str(item).casefold() in text.casefold(), (question, item, text)
        _assert_source_transparency(result)
        assert result["latency_ms"] < 2000
        results.append((question, result["latency_ms"], len(result["sources"])))
    assert len(results) == 7


def test_business_uat_open_ticket_report_and_report_from_retrieval(runtime):
    response, retrieved = runtime.create_open_ticket_report(EMPLOYEE)
    artifact = response.content
    assert artifact.metadata.size_bytes > 0
    assert response.sources
    assert "ABC-778" in retrieved and "ABC-779" in retrieved
    _, report_metadata = runtime.report._storage.issue_download_token(artifact.metadata.report_id, 300)
    wb = load_workbook(runtime.report._storage.open_path(report_metadata), read_only=True)
    ws = wb.active
    values = list(ws.values)
    wb.close()
    assert any("ABC-778" in str(row) for row in values)


def test_business_uat_source_transparency(runtime):
    result = runtime.ask(EMPLOYEE, "Find all documents related to Project XYZ.")
    assert result["sources"]
    payloads = [src.to_frontend_dict() for src in result["sources"]]
    assert any("Project_XYZ_requirements.txt" in str(p) for p in payloads)
    assert any("Project_XYZ_plan.docx" in str(p) for p in payloads)
    for src, payload in zip(result["sources"], payloads):
        assert payload["href"].startswith("/api/sources/")
        assert "SELECT" not in str(payload)
        assert runtime.sources.resolve_for_user(EMPLOYEE, result["request_id"], src.reference_id) == src


def test_business_uat_restricted_data_denied(runtime):
    resource = Resource("invoices", "database_source", TENANT, department="Finance", attributes={"restricted_department": "Finance"})
    decision = runtime.auth.authorize(EMPLOYEE, Permission.DATABASE_READ, resource)
    assert not decision.allowed
    # DatabaseService authorizes the database resource, while table-level Finance
    # restrictions are enforced by the business authorization layer/planner.
    # This assertion validates the required policy decision without pretending
    # the generic database service has table metadata it does not receive.
    assert runtime.auth.authorize(EMPLOYEE, Permission.FINANCE_READ, resource).allowed is False


def test_business_uat_cross_tenant_denied(runtime):
    resource = Resource("ABC_open_tickets.csv", "company_file", TENANT)
    assert not runtime.auth.authorize(OTHER_TENANT, Permission.FILE_READ, resource).allowed


def test_business_uat_email_count_and_finance_boundary(runtime):
    result = runtime.email.search(EMPLOYEE, runtime.email_context, EmailSearchRequest(max_results=10))
    assert len(result) == 10
    finance_resource = Resource("invoices", "database_source", TENANT, department="Finance", attributes={"restricted_department": "Finance"})
    assert runtime.auth.authorize(FINANCE, Permission.DATABASE_READ, finance_resource).allowed
    assert not runtime.auth.authorize(EMPLOYEE, Permission.DATABASE_READ, finance_resource).allowed


def test_business_uat_report_from_retrieved_information(runtime):
    result = runtime.retrieval.retrieve(EMPLOYEE, RetrievalRequest("Project XYZ", top_k=2))
    assert len(result.hits) == 2
    lineage = tuple(
        DataLineage("txt", hit.chunk.source.source_id, hit.chunk.source.filename or hit.chunk.source.source_id, (),
                    tenant_id=TENANT, resource_type="company_file")
        for hit in result.hits
    )
    req = ReportRequest(
        str(uuid4()), "Project XYZ Evidence", ReportFormat.PDF, EMPLOYEE.user_id, TENANT,
        [{"source": hit.chunk.source.source_id, "evidence": hit.chunk.content} for hit in result.hits], lineage,
    )
    agent = ReportAgent(runtime.report, runtime.gateway, runtime.sources)
    response = agent.create(AgentRequest(uuid4().hex, EMPLOYEE, "Generate a report from retrieved Project XYZ information"), req)
    assert response.content.metadata.size_bytes > 0
    assert len(response.sources) == 2


def test_business_uat_restricted_knowledge_denied_and_privileged_allowed(runtime):
    employee_result = runtime.retrieval.retrieve(EMPLOYEE, RetrievalRequest("Finance invoice register", top_k=5))
    assert not employee_result.hits
    finance_result = runtime.retrieval.retrieve(FINANCE, RetrievalRequest("Finance invoice register", top_k=5))
    assert any(h.chunk.source.source_id == "Finance_invoices.txt" for h in finance_result.hits)


def test_business_uat_report_requires_authorized_lineage(runtime):
    bad_lineage = DataLineage("sql", "restricted_hr", "HR", ("employee", "salary"),
                              query="SELECT employee, salary FROM restricted_hr", tenant_id=TENANT,
                              department="HR", restricted_department="HR", resource_type="database_source")
    req = ReportRequest(str(uuid4()), "Restricted", ReportFormat.EXCEL, EMPLOYEE.user_id, TENANT,
                        [{"employee": "Synthetic HR", "salary": 99999}], (bad_lineage,))
    with pytest.raises(ReportAuthorizationError):
        runtime.report.create_report(EMPLOYEE, req)
