"""Tests for comprehensive multi-format document support:
PDF, Word (.docx, .doc), Excel (.xlsx, .xls, .xlsm, .csv, .tsv),
Text (.txt, .md, .log), PowerPoint (.pptx, .ppt), RTF (.rtf),
JSON (.json, .jsonl), XML (.xml), HTML (.html).
"""
import pytest
from backend.integrations.files.company_data.extraction import create_default_document_service
from backend.documents.preview_renderer import render_document_to_html
from backend.api.chat_routes import ALLOWED_EXTENSIONS


def test_allowed_extensions_covers_all_formats():
    """Verify that all enterprise file formats are in ALLOWED_EXTENSIONS."""
    expected = {
        ".pdf",
        ".doc", ".docx",
        ".xls", ".xlsx", ".xlsm",
        ".csv", ".tsv",
        ".txt", ".text", ".md", ".log",
        ".rtf",
        ".json", ".jsonl",
        ".xml",
        ".html", ".htm",
        ".ppt", ".pptx",
    }
    for ext in expected:
        assert ext in ALLOWED_EXTENSIONS, f"Expected {ext} in ALLOWED_EXTENSIONS"


def test_csv_parser():
    svc = create_default_document_service()
    data = b"Vendor,Amount,Status\nAcme Corp,$12000,Paid\nBeta LLC,$5000,Pending"
    doc = svc.parse_bytes(filename="invoices.csv", relative_path="invoices.csv", data=data)
    assert doc.tables
    assert doc.tables[0].headers == ["Vendor", "Amount", "Status"]
    assert len(doc.tables[0].rows) == 2
    html = render_document_to_html(doc)
    assert "Acme Corp" in html
    assert "data-table" in html


def test_tsv_parser():
    svc = create_default_document_service()
    data = b"Item\tQty\tPrice\nWidget\t10\t$25\nGadget\t5\t$100"
    doc = svc.parse_bytes(filename="items.tsv", relative_path="items.tsv", data=data)
    assert doc.tables
    assert doc.tables[0].headers == ["Item", "Qty", "Price"]
    html = render_document_to_html(doc)
    assert "Widget" in html


def test_text_and_markdown_parser():
    svc = create_default_document_service()
    data = b"# Employee Handbook\n\nAll employees receive 20 days PTO."
    doc = svc.parse_bytes(filename="handbook.md", relative_path="handbook.md", data=data)
    assert "Employee Handbook" in doc.text
    html = render_document_to_html(doc)
    assert "Employee Handbook" in html


def test_rtf_parser():
    svc = create_default_document_service()
    data = b"{\\rtf1\\ansi\\deff0{\\fonttbl{\\f0 Courier;}}\\b Executive Summary\\b0\\par Revenue grew by 25% this quarter.}"
    doc = svc.parse_bytes(filename="summary.rtf", relative_path="summary.rtf", data=data)
    assert "Executive Summary" in doc.text
    assert "Revenue grew by 25%" in doc.text


def test_json_parser():
    svc = create_default_document_service()
    data = b'{"tenant": "enterprise", "plan": "tier-1", "users": 150}'
    doc = svc.parse_bytes(filename="config.json", relative_path="config.json", data=data)
    assert "tier-1" in doc.text
    html = render_document_to_html(doc)
    assert "tier-1" in html


def test_xml_parser():
    svc = create_default_document_service()
    data = b"<records><record><id>REC-001</id><title>Project Falcon</title></record></records>"
    doc = svc.parse_bytes(filename="data.xml", relative_path="data.xml", data=data)
    assert "Project Falcon" in doc.text


def test_html_parser():
    svc = create_default_document_service()
    data = b"<html><head><title>Test</title></head><body><h1>Release Notes</h1><p>Version 2.0 deployed.</p></body></html>"
    doc = svc.parse_bytes(filename="notes.html", relative_path="notes.html", data=data)
    assert "Release Notes" in doc.text
    assert "Version 2.0" in doc.text


def test_legacy_doc_parser():
    svc = create_default_document_service()
    data = b"\xd0\xcf\x11\xe0" + "Master Services Agreement between Provider and Client.\nSection 1: Confidentiality.".encode("utf-16le")
    doc = svc.parse_bytes(filename="agreement.doc", relative_path="agreement.doc", data=data)
    assert "Master Services Agreement" in doc.text
    html = render_document_to_html(doc)
    assert "Master Services Agreement" in html


def test_legacy_xls_parser():
    svc = create_default_document_service()
    data = b"<html><body><table><tr><th>Department</th><th>Budget</th></tr><tr><td>Engineering</td><td>$500k</td></tr></table></body></html>"
    doc = svc.parse_bytes(filename="budget.xls", relative_path="budget.xls", data=data)
    assert doc.tables
    assert doc.tables[0].headers == ["Department", "Budget"]
    html = render_document_to_html(doc)
    assert "Engineering" in html


def test_legacy_ppt_parser():
    svc = create_default_document_service()
    data = b"\xd0\xcf\x11\xe0" + b"Slide 1: Strategy 2026\nQuarterly OKRs and Roadmap Goals"
    doc = svc.parse_bytes(filename="presentation.ppt", relative_path="presentation.ppt", data=data)
    assert "Strategy 2026" in doc.text
    html = render_document_to_html(doc)
    assert "Strategy 2026" in html

