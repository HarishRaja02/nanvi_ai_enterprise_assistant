from datetime import datetime, timezone

import pytest

from backend.analysis.models import DataLineage
from backend.security.audit import AuditLogger, InMemoryAuditSink
from backend.security.authorization import AuthorizationService, UserAttributes
from backend.security.authorization.rbac import Role
from backend.sources.models import SourceType
from backend.sources.service import SourceReferenceNotFound, SourceReferenceService
from backend.sources.store import InMemorySourceReferenceStore


def user(role=Role.EMPLOYEE, user_id="u1", tenant="t1", department="Projects"):
    return UserAttributes(user_id, tenant, department, frozenset({role}))


def service():
    sink = InMemoryAuditSink()
    audit = AuditLogger(sink)
    svc = SourceReferenceService(AuthorizationService(), audit, InMemorySourceReferenceStore())
    return svc, sink


def test_file_source_reference_is_frontend_safe_and_clickable():
    svc, _ = service()
    refs = svc.from_lineage(user(), "req-1", (
        DataLineage("file", "Finance/AccountsReceivable.xlsx", "AccountsReceivable.xlsx", ("invoice", "amount"),
                    filters=("status = overdue",), tenant_id="t1", department="Finance", restricted_department="Finance"),
    ))
    # Employee in Projects cannot see Finance source metadata.
    assert refs == ()

    refs = svc.from_lineage(user(department="Finance"), "req-2", (
        DataLineage("file", "Finance/AccountsReceivable.xlsx", "AccountsReceivable.xlsx", ("invoice", "amount"),
                    filters=("status = overdue",), tenant_id="t1", department="Finance", restricted_department="Finance"),
    ))
    assert len(refs) == 1
    payload = refs[0].to_frontend_dict()
    assert payload["display_name"] == "AccountsReceivable.xlsx"
    assert payload["href"].startswith("/api/sources/")
    assert "Finance/" not in payload["href"]


def test_database_reference_never_exposes_sql_or_record_data():
    svc, _ = service()
    refs = svc.from_lineage(user(), "req-3", (
        DataLineage("sql", "prod-db", "Accounts Receivable", ("invoice", "amount"),
                    query="SELECT * FROM finance.invoices WHERE amount > 10000",
                    tenant_id="t1", department="Finance"),
    ))
    assert len(refs) == 1
    payload = refs[0].to_frontend_dict()
    assert payload["source_type"] == SourceType.DATABASE.value
    assert "SELECT" not in str(payload)
    assert "prod-db" not in str(payload)
    assert "10000" not in str(payload)
    assert payload["display_name"] == "Accounts Receivable"


def test_email_reference_exposes_metadata_but_not_body():
    svc, _ = service()
    refs = svc.from_lineage(user(), "req-4", (
        DataLineage("email", "opaque-message-id", "Finance email — Aug 12", (),
                    tenant_id="t1"),
    ))
    assert len(refs) == 1
    payload = refs[0].to_frontend_dict()
    assert payload["display_name"] == "Finance email — Aug 12"
    assert "opaque-message-id" not in str(payload)


def test_reference_is_reauthorized_on_click_and_denial_does_not_leak():
    svc, sink = service()
    refs = svc.from_lineage(user(), "req-5", (
        DataLineage("file", "Projects/plan.xlsx", "plan.xlsx", (), tenant_id="t1"),
    ))
    ref = refs[0]
    assert svc.resolve_for_user(user(), "req-6", ref.reference_id) == ref

    with pytest.raises(SourceReferenceNotFound):
        svc.resolve_for_user(user(user_id="u2", tenant="t2"), "req-7", ref.reference_id)
    assert any(e.event_type == "source_reference_access" and e.outcome == "deny" for e in sink.events)


def test_website_is_reserved_for_later():
    svc, _ = service()
    refs = svc.from_lineage(user(), "req-8", (
        DataLineage("website", "https://example.com", "Example", (), tenant_id="t1"),
    ))
    assert refs == ()
