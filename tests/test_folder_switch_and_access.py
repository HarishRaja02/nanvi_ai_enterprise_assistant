import pytest
from pathlib import Path
from backend.integrations.files.company_data_service import CompanyDataService, get_persisted_folder
from backend.security.authorization import UserAttributes
from backend.security.authorization.rbac import Role
from backend.bootstrap import create_chat_service
from backend.chat.models import ChatRequest


@pytest.fixture(autouse=True)
def restore_company_data():
    yield
    if Path("C:/CompanyData").exists():
        CompanyDataService.get_instance("C:/CompanyData")


def test_folder_switch_and_persistence(tmp_path):
    # Create custom temporary directory with files
    doc1 = tmp_path / "custom_policy.md"
    doc1.write_text("# Remote Work Policy\nEmployees may work remotely on Fridays with manager approval.")
    doc2 = tmp_path / "financial_invoice.txt"
    doc2.write_text("Invoice ID: INV-99001\nTotal Amount: $4,500.00\nStatus: Pending\nDue Date: 2026-10-15\nCustomer: Delta Inc")

    cds = CompanyDataService.get_instance()
    cds.update_root(tmp_path)

    # 1. Verify persistence
    persisted = get_persisted_folder()
    assert persisted is not None
    assert persisted.resolve() == tmp_path.resolve()

    # 2. Verify files indexed
    assert len(cds.files) == 2
    assert len(cds.chunks) >= 2

    # 3. Verify RBAC allows employee access to general files
    user = UserAttributes("user1", "enterprise-tenant", "General", (Role.EMPLOYEE,))
    for chunk in cds.chunks:
        assert cds.is_folder_authorized(user, chunk.folder) is True

    # 4. Search local files directly
    res = cds.search(user, "what is the remote work policy?")
    assert res.is_exact_match is True
    assert len(res.sources) >= 1
    assert "remote" in res.answer_content.lower()

    # 5. Test search_files
    file_res = cds.search_files(user, "find custom_policy.md")
    assert file_res.is_exact_match is True
    assert len(file_res.sources) >= 1

    # 6. Test invoice extraction
    inv_recs, inv_sources = cds.extract_invoice_records(user)
    assert len(inv_recs) == 1
    assert inv_recs[0]["id"] == "INV-99001"


def test_chat_service_retrieves_from_new_folder_without_web_fallback(tmp_path):
    doc = tmp_path / "HANDOVER_NOTES.md"
    doc.write_text("# Enterprise Handover Notes\nThe system migration was completed successfully on 2026-09-20. All services are healthy.")

    cds = CompanyDataService.get_instance()
    cds.update_root(tmp_path)

    cs = create_chat_service()
    user = UserAttributes("user1", "enterprise-tenant", "Engineering", (Role.EMPLOYEE,))

    response = cs.ask(user, ChatRequest("summarize HANDOVER_NOTES.md"))

    # Capability must be knowledge, NOT web_search
    assert "knowledge" in response.capability
    assert "web_search" not in response.capability
    assert len(response.sources) >= 1
    assert any("HANDOVER_NOTES" in s.title or "HANDOVER_NOTES" in s.display_name for s in response.sources)
    assert not any("web_search" in t for t in response.trace)
