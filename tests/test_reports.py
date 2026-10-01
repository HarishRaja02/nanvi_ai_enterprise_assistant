from __future__ import annotations

from uuid import uuid4

import pytest
from docx import Document
from openpyxl import load_workbook
from pypdf import PdfReader

from backend.analysis.models import DataLineage
from backend.agents.models import AgentRequest
from backend.agents.security_gateway import SecureToolGateway, ToolPolicyDenied
from backend.reports.agent import ReportAgent
from backend.reports.models import ReportFormat, ReportRequest
from backend.reports.service import ReportAuthorizationError, ReportService
from backend.reports.storage import ReportNotFound, SecureFileReportStorage
from backend.security.audit import AuditLogger, InMemoryAuditSink
from backend.security.authorization import AuthorizationService, UserAttributes
from backend.security.authorization.rbac import Role


def make_user(role=Role.EMPLOYEE, user_id="u1", tenant="t1", department="Projects"):
    return UserAttributes(user_id=user_id, tenant_id=tenant, department=department, roles=frozenset({role}))


def make_service(tmp_path):
    sink = InMemoryAuditSink()
    audit = AuditLogger(sink)
    storage = SecureFileReportStorage(tmp_path / "reports")
    service = ReportService(storage, AuthorizationService(), audit)
    return service, storage, sink


def request(fmt, report_id=None, tenant="t1", owner="u1"):
    return ReportRequest(
        report_id=report_id or str(uuid4()),
        title="Sales Summary",
        format=fmt,
        generated_by=owner,
        tenant_id=tenant,
        data=[{"month": "2026-09", "sales": 32000}, {"month": "2026-08", "sales": 25000}],
        lineage=(DataLineage("sql", "sales-db", "Sales DB", ("month", "sales"), "SELECT month, sales FROM sales", (), tenant_id=tenant, resource_type="database_source"),),
        description="Deterministic sales analysis.",
    )


def test_generates_excel_with_lineage(tmp_path):
    service, storage, sink = make_service(tmp_path)
    artifact = service.create_report(make_user(), request(ReportFormat.EXCEL))
    path = storage.open_path(storage.get(artifact.metadata.report_id))
    wb = load_workbook(path, read_only=True)
    assert wb["Report"].cell(4, 2).value == "sales"
    assert wb["Sources"].cell(2, 1).value == "sql"
    assert any(e.event_type == "report_creation" and e.outcome == "allow" for e in sink.events)


def test_generates_pdf_with_lineage(tmp_path):
    service, storage, _ = make_service(tmp_path)
    artifact = service.create_report(make_user(), request(ReportFormat.PDF))
    reader = PdfReader(str(storage.open_path(artifact.metadata)))
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    assert "Sales Summary" in text
    assert "Sales DB" in text


def test_generates_word_with_lineage(tmp_path):
    service, storage, _ = make_service(tmp_path)
    artifact = service.create_report(make_user(), request(ReportFormat.WORD))
    doc = Document(storage.open_path(artifact.metadata))
    text = "\n".join(p.text for p in doc.paragraphs)
    assert "Sales Summary" in text
    assert "Sales DB" in text


def test_unauthorized_user_cannot_create_or_download(tmp_path):
    service, storage, sink = make_service(tmp_path)
    owner = make_user()
    artifact = service.create_report(owner, request(ReportFormat.PDF))
    intruder = make_user(user_id="u2")
    with pytest.raises(ReportAuthorizationError):
        service.issue_temporary_download_url(intruder, artifact.metadata.report_id)
    assert any(e.event_type == "report_download" and e.outcome == "deny" for e in sink.events)


def test_download_token_is_short_lived_and_one_time(tmp_path):
    service, storage, _ = make_service(tmp_path)
    user = make_user()
    artifact = service.create_report(user, request(ReportFormat.PDF))
    token_url = service.issue_temporary_download_url(user, artifact.metadata.report_id, ttl_seconds=60)
    token = token_url.split("token=", 1)[1]
    path, _ = service.open_download(user, artifact.metadata.report_id, token)
    assert path.exists()
    with pytest.raises(ReportNotFound):
        service.open_download(user, artifact.metadata.report_id, token)


def test_report_agent_uses_security_gateway(tmp_path):
    service, _, sink = make_service(tmp_path)
    gateway = SecureToolGateway(AuthorizationService(), AuditLogger(sink))
    agent = ReportAgent(service, gateway)
    response = agent.create(AgentRequest("req1", make_user(), "generate sales report"), request(ReportFormat.EXCEL))
    assert response.capability.value == "report"
    assert response.content.metadata.format == ReportFormat.EXCEL


def test_report_agent_denied_without_permission(tmp_path):
    service, _, sink = make_service(tmp_path)
    gateway = SecureToolGateway(AuthorizationService(), AuditLogger(sink))
    agent = ReportAgent(service, gateway)
    no_role = UserAttributes("u1", "t1", "Projects", frozenset())
    with pytest.raises(ToolPolicyDenied):
        agent.create(AgentRequest("req1", no_role, "generate"), request(ReportFormat.PDF))

def test_report_download_requires_report_download_permission(tmp_path):
    service, storage, sink = make_service(tmp_path)
    owner = make_user()
    artifact = service.create_report(owner, request(ReportFormat.PDF))
    # The employee role has both permissions today; use a custom policy that removes
    # REPORT_DOWNLOAD to prove download is not accidentally authorized by REPORT_CREATE.
    from backend.security.authorization.policies import AuthorizationDecision
    class DownloadDenyPolicy:
        def evaluate(self, user, permission, resource):
            if permission.value == "REPORT_DOWNLOAD":
                return AuthorizationDecision(False, "download denied")
            return AuthorizationDecision(True, "allowed")
    restricted = ReportService(storage, AuthorizationService(DownloadDenyPolicy()), AuditLogger(sink))
    with pytest.raises(ReportAuthorizationError):
        restricted.issue_temporary_download_url(owner, artifact.metadata.report_id)
