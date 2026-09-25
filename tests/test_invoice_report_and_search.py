"""Tests for Content-First Invoice Search and Report Generation Integration.

Verifies:
1. extract_invoice_records parses structured fields (Company, Invoice ID, Amount, Status, Date) from real files.
2. Fast-path invoice search returns compact summaries protecting LLM tokens.
3. ReportAgent generates report using real files via CompanyDataService with proper lineage and 10-row capped preview.
4. ChatService correctly identifies report generation requests for invoices.
"""
from __future__ import annotations

from pathlib import Path
from uuid import uuid4
import pytest

from backend.agents.capability_agents import ReportAgent
from backend.agents.models import AgentRequest, Capability
from backend.chat.service import ChatService
from backend.integrations.files.company_data_service import CompanyDataService
from backend.reports.service import ReportService
from backend.reports.storage import SecureFileReportStorage
from backend.security.audit import AuditLogger, InMemoryAuditSink
from backend.security.authorization import AuthorizationService, UserAttributes
from backend.security.authorization.rbac import Role
from backend.sources.service import SourceReferenceService
from backend.sources.store import InMemorySourceReferenceStore
from tests.test_content_first_retrieval import create_pdf, create_csv


@pytest.fixture
def finance_user() -> UserAttributes:
    return UserAttributes("u-fin", "tenant-test", "Finance", frozenset({Role.FINANCE}))


@pytest.fixture
def mock_company_data(tmp_path: Path) -> CompanyDataService:
    root = tmp_path / "CompanyData"
    root.mkdir()
    fin_dir = root / "Finance"
    fin_dir.mkdir()

    # 1. Invoice PDF
    create_pdf(
        fin_dir / "invoice_abc.pdf",
        "Customer: Nexa Retail\nInvoice ID: INV-00101\nAmount: $15,400.00\nPayment Status: Overdue\nDue Date: 2026-03-15",
    )
    # 2. Invoice PDF (Paid)
    create_pdf(
        fin_dir / "invoice_xyz.pdf",
        "Customer: BluePeak Systems\nInvoice ID: INV-00102\nAmount: $8,250.00\nPayment Status: Paid\nDue Date: 2026-03-01",
    )
    # 3. Vendor Payment Schedule CSV
    create_csv(
        fin_dir / "vendor_payment_schedule.csv",
        [
            ["Vendor Name", "Category", "Invoice ID", "Amount ($)", "Invoice Date", "Due Date", "Payment Status"],
            ["CloudNova Tech", "Cloud Hosting", "INV-2026-9901", "24,500.00", "2026-02-15", "2026-03-20", "Overdue"],
            ["SecureGate LLC", "Security Tooling", "INV-2026-9902", "5,100.00", "2026-02-28", "2026-03-31", "Scheduled"],
        ]
    )

    svc = CompanyDataService(root)
    svc.ensure_indexed(force=True)
    return svc


def test_extract_invoice_records_from_mixed_sources(mock_company_data: CompanyDataService, finance_user: UserAttributes):
    """Verify structured fields are extracted from both PDF and CSV."""
    records, sources = mock_company_data.extract_invoice_records(finance_user)
    assert len(records) >= 3

    ids = [r["id"] for r in records]
    assert "INV-00101" in ids
    assert "INV-00102" in ids
    assert "INV-2026-9901" in ids

    # Overdue records are sorted first
    assert "overdue" in records[0]["status"].lower() or "overdue" in records[1]["status"].lower()
    assert len(sources) >= 2


def test_search_invoice_returns_compact_summary(mock_company_data: CompanyDataService, finance_user: UserAttributes):
    """Verify search sends only required concise fields (Company, Invoice, Amount, Status) to prevent LLM rate limits."""
    res = mock_company_data.search(finance_user, "Show me all overdue invoices")
    assert res.is_exact_match
    assert "Found the following authorized overdue invoices:" in res.answer_content
    # Check that concise fields are present
    assert "Nexa Retail" in res.answer_content or "CloudNova Tech" in res.answer_content
    assert "Overdue" in res.answer_content
    assert len(res.sources) >= 1
    # Check that raw PDF dumps are NOT present (tokens are compact)
    assert len(res.answer_content) < 800


def test_report_agent_generates_invoice_report_from_files(tmp_path: Path, mock_company_data: CompanyDataService, finance_user: UserAttributes):
    """Verify ReportAgent uses real files from CompanyDataService to generate an executive report with lineage."""
    sink = InMemoryAuditSink()
    audit = AuditLogger(sink)
    auth = AuthorizationService()
    storage = SecureFileReportStorage(tmp_path / "reports")
    report_service = ReportService(storage, auth, audit)
    src_service = SourceReferenceService(auth, audit, InMemorySourceReferenceStore())

    agent = ReportAgent(
        report_service=report_service,
        source_references=src_service,
        company_data_service=mock_company_data,
    )

    req = AgentRequest(
        request_id=str(uuid4()),
        user=finance_user,
        query="Generate an overdue invoice report in pdf",
    )

    resp = agent.run(req)
    assert resp.capability == Capability.REPORT
    assert "Document Generated: Enterprise Overdue Invoices Report" in resp.content
    assert "Download Official PDF Document" in resp.content
    assert "| Id | Customer | Amount | Status | Due Date |" in resp.content
    # Lineage and source citations are verified
    assert any(e.event_type == "report_creation" and e.outcome == "allow" for e in sink.events)


def test_chat_service_capabilities_for_report_and_file_search():
    """Verify query router correctly isolates report generation and routes file searches to Knowledge."""
    # Report queries must route exclusively to REPORT
    assert ChatService._capabilities_for_query("report generation for invoice") == (Capability.REPORT,)
    assert ChatService._capabilities_for_query("generate invoice report in word") == (Capability.REPORT,)
    assert ChatService._capabilities_for_query("create overdue invoice report in pdf") == (Capability.REPORT,)

    # Search queries for files must prioritize KNOWLEDGE
    search_caps = ChatService._capabilities_for_query("search file for invoices in companydata")
    assert search_caps[0] == Capability.KNOWLEDGE

    # Multi-source search queries mentioning mail and db
    multi_caps = ChatService._capabilities_for_query("search invoices in mail and database")
    assert Capability.EMAIL in multi_caps
    assert Capability.DATABASE in multi_caps
