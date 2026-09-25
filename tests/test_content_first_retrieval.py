"""Tests for Content-First Document Retrieval Pipeline.

Verifies:
1. Generic filename with matching content is retrieved.
2. Misleading filename with non-matching content is not retrieved.
3. Deeply nested subfolders are discovered and searched regardless of folder names.
4. Multiple file types (PDF, DOCX, XLSX, CSV, TXT, MD) are searched and retrieved for cross-file queries.
5. Department RBAC isolation is strictly enforced.
6. Structured document metadata is properly populated.
7. Completely unrelated queries return empty results rather than irrelevant files.
"""
from __future__ import annotations

import csv
from pathlib import Path
import pytest
from docx import Document as DocxDocument
from openpyxl import Workbook
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate

from backend.integrations.files.company_data_service import CompanyDataService
from backend.security.authorization import UserAttributes
from backend.security.authorization.rbac import Role


def create_pdf(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(str(path), pagesize=letter)
    styles = getSampleStyleSheet()
    story = []
    for line in content.strip().split("\n"):
        if line.strip():
            story.append(Paragraph(line.strip(), styles["Normal"]))
    doc.build(story)


def create_docx(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = DocxDocument()
    for line in content.strip().split("\n"):
        if line.strip():
            doc.add_paragraph(line.strip())
    doc.save(str(path))


def create_xlsx(path: Path, sheet_name: str, rows: list[list[str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    wb = Workbook()
    ws = wb.active
    ws.title = sheet_name
    for row in rows:
        ws.append(row)
    wb.save(str(path))


def create_csv(path: Path, rows: list[list[str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerows(rows)


def create_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


@pytest.fixture
def ceo_user() -> UserAttributes:
    return UserAttributes("u-ceo", "tenant-test", "Executive", frozenset({Role.CEO}))


@pytest.fixture
def employee_user() -> UserAttributes:
    return UserAttributes("u-emp", "tenant-test", "Projects", frozenset({Role.EMPLOYEE}))


@pytest.fixture
def test_company_root(tmp_path: Path) -> Path:
    """Create test company directories with misleading and generic names."""
    company_dir = tmp_path / "CompanyData"
    company_dir.mkdir()

    # Finance department
    # Test 1: Generic filename containing actual ABC Company invoice content
    create_pdf(
        company_dir / "Finance" / "random123.pdf",
        "Customer: ABC Company\nInvoice: INV-1001\nAmount: ₹75,000\nStatus: Paid\nDate: 2026-03-01",
    )

    # Test 2: Misleading filename whose content is actually about XYZ Company
    create_pdf(
        company_dir / "Finance" / "ABC_Company.pdf",
        "Customer: XYZ Company\nInvoice: INV-9999\nAmount: $10,000\nStatus: Pending",
    )

    # Test 3: Deeply nested subfolders (Finance/hi/test/random/data.pdf)
    create_pdf(
        company_dir / "Finance" / "hi" / "test" / "random" / "data.pdf",
        "Customer: ABC Company\nInvoice: INV-2005\nAmount: ₹1,50,000\nDepartment: Enterprise Services",
    )

    # Test 4: Cross-file formats in Customers and Projects
    # DOCX
    create_docx(
        company_dir / "Customers" / "file123.docx",
        "ABC Company Account Details\nPrimary Account Manager: John Doe\nSLA Tier: 99.95%\nRenewal Month: December",
    )

    # XLSX
    create_xlsx(
        company_dir / "Projects" / "abc.xlsx",
        "Financials",
        [
            ["Company", "Annual_ARR", "Employees", "Lead_Engineer"],
            ["ABC Company", "$500,000", "120", "Rahul Patel"],
            ["Acme Global", "$350,000", "80", "Sarah Jenkins"],
        ],
    )

    # CSV
    create_csv(
        company_dir / "Customers" / "data.csv",
        [
            ["Company", "Contract_ID", "Terms"],
            ["ABC Company", "CNT-8821", "3-Year Multi-Region Enterprise Agreement"],
            ["Beta LLC", "CNT-1102", "Annual Pilot"],
        ],
    )

    # TXT in nested HR
    create_text(
        company_dir / "HR" / "something" / "notes.txt",
        "Candidate Interview Schedule for ABC Company Account Team: Alice Smith, Bob Jones.",
    )

    return company_dir


def test_01_generic_filename_retrieved_by_content(test_company_root: Path, ceo_user: UserAttributes):
    """Test 1: File random123.pdf has generic filename but contains ABC Company invoice."""
    svc = CompanyDataService(test_company_root)
    svc.ensure_indexed(force=True)

    result = svc.search(ceo_user, "What is ABC Company's invoice amount?")
    assert result.is_exact_match
    assert result.answer_content
    # The content from random123.pdf must be in answer
    assert "75,000" in result.answer_content or "INV-1001" in result.answer_content
    # random123.pdf must be in the sources
    filenames = [s.display_name for s in result.sources]
    assert any("random123.pdf" in f for f in filenames)


def test_02_misleading_filename_is_not_trusted(test_company_root: Path, ceo_user: UserAttributes):
    """Test 2: ABC_Company.pdf contains XYZ Company content.

    Query asking about ABC Company should NOT retrieve ABC_Company.pdf.
    """
    svc = CompanyDataService(test_company_root)
    svc.ensure_indexed(force=True)

    result = svc.search(ceo_user, "What information do we have about ABC Company?")
    assert result.is_exact_match
    # The misleading file ABC_Company.pdf (which only has XYZ Company content) must NOT be in sources
    for source in result.sources:
        assert "ABC_Company.pdf" not in source.display_name
        assert "INV-9999" not in result.answer_content


def test_03_deeply_nested_folders_recursively_discovered(test_company_root: Path, ceo_user: UserAttributes):
    """Test 3: Finance/hi/test/random/data.pdf must be discovered regardless of nesting depth."""
    svc = CompanyDataService(test_company_root)
    svc.ensure_indexed(force=True)

    result = svc.search(ceo_user, "Find the invoice information for ABC Company INV-2005")
    assert result.is_exact_match
    assert "INV-2005" in result.answer_content
    assert "1,50,000" in result.answer_content
    filenames = [s.display_name for s in result.sources]
    assert any("data.pdf" in f for f in filenames)


def test_04_cross_file_multiple_formats_retrieved(test_company_root: Path, ceo_user: UserAttributes):
    """Test 4: Information spread across PDF, DOCX, XLSX, and CSV about the same company."""
    svc = CompanyDataService(test_company_root)
    svc.ensure_indexed(force=True)

    result = svc.search(ceo_user, "Give me all available information about ABC Company")
    assert result.is_exact_match
    assert len(result.top_chunks) >= 2

    # Verify content from multiple file formats is retrieved
    retrieved_content = result.answer_content
    has_pdf = "INV-1001" in retrieved_content or "INV-2005" in retrieved_content
    has_docx = "John Doe" in retrieved_content or "99.95%" in retrieved_content
    has_xlsx = "Rahul Patel" in retrieved_content or "500,000" in retrieved_content
    has_csv = "CNT-8821" in retrieved_content

    # At least 3 different formats must be successfully included in the cross-file answer
    matching_formats = sum([has_pdf, has_docx, has_xlsx, has_csv])
    assert matching_formats >= 3, f"Expected cross-file content from multiple formats, got {matching_formats}"


def test_05_department_isolation_preserved(test_company_root: Path, employee_user: UserAttributes, ceo_user: UserAttributes):
    """Test 5: Employee user (only Projects role) cannot access Finance invoices."""
    svc = CompanyDataService(test_company_root)
    svc.ensure_indexed(force=True)

    # Employee asks about Finance invoice INV-1001
    emp_result = svc.search(employee_user, "What is the invoice amount for INV-1001?")
    # Must NOT return Finance/random123.pdf
    for src in emp_result.sources:
        assert "Finance" not in src.display_name

    # CEO has access to Finance
    ceo_result = svc.search(ceo_user, "What is the invoice amount for INV-1001?")
    assert ceo_result.is_exact_match
    assert any("random123.pdf" in s.display_name for s in ceo_result.sources)


def test_06_metadata_model_structure(test_company_root: Path):
    """Test 6: Verify indexed files dictionary contains all required metadata fields."""
    svc = CompanyDataService(test_company_root)
    svc.ensure_indexed(force=True)

    assert len(svc._indexed_files) >= 5
    for file_id, meta in svc._indexed_files.items():
        assert "file_id" in meta
        assert "filename" in meta
        assert "file_path" in meta
        assert "department" in meta
        assert "folder_path" in meta
        assert "file_type" in meta
        assert "content" in meta
        assert "chunks" in meta
        assert "created_at" in meta
        assert "modified_at" in meta
        assert "size_bytes" in meta
        assert meta["content"], f"Content should not be empty for {file_id}"


def test_07_unrelated_query_returns_empty_result(test_company_root: Path, ceo_user: UserAttributes):
    """Test 7: A query with no matching content in the corpus returns empty result."""
    svc = CompanyDataService(test_company_root)
    svc.ensure_indexed(force=True)

    result = svc.search(ceo_user, "Quantum mechanics teleportation coordinates in Antarctica")
    assert not result.is_exact_match
    assert result.answer_content == ""
    assert len(result.sources) == 0
