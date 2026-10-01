"""Tests for Phase 1 P0 Security and Correctness:
1. Production fallback data removal and synthetic data gating/labeling.
2. Gmail provider and EmailAgent fail-closed behavior when no mailbox connected.
3. SQLite repository rejection in production.
"""
from __future__ import annotations

import dataclasses
import sys
import pytest
from unittest.mock import MagicMock, patch

from backend.agents.models import AgentRequest, Capability
from backend.agents.capability_agents import ReportAgent, EmailAgent
from backend.core.config import Settings
import backend.core.config as config_mod
from backend.core.exceptions import ConfigurationError, DependencyUnavailableError
from backend.security.authorization import UserAttributes
from backend.security.authorization.rbac import Role
from backend.integrations.email.models import EmailProviderContext, EmailSearchRequest
from backend.integrations.email.gmail import GmailEmailProvider
from backend.integrations.database.sqlite import SQLiteEnterpriseRepository


def patch_settings(monkeypatch: pytest.MonkeyPatch, **kwargs) -> Settings:
    """Helper to update frozen settings across all module references."""
    new_settings = dataclasses.replace(config_mod.settings, **kwargs)
    monkeypatch.setattr(config_mod, "settings", new_settings)
    return new_settings


@pytest.fixture
def enterprise_user() -> UserAttributes:
    return UserAttributes(
        user_id="user-corp-01",
        tenant_id="tenant-prod-corp",
        department="Finance",
        roles=frozenset({Role.FINANCE, Role.EMPLOYEE}),
    )


@pytest.fixture
def mock_report_service():
    svc = MagicMock()
    svc.create_report.return_value = MagicMock(artifact_id="rep-123")
    svc.issue_temporary_download_url.return_value = "https://nanvi.enterprise/downloads/rep-123.pdf"
    return svc


def test_synthetic_fixtures_module_forbidden_in_production(monkeypatch):
    """Importing synthetic fixtures module in production must raise ConfigurationError."""
    patch_settings(monkeypatch, app_mode="production")
    
    # Remove from sys.modules if already imported
    sys.modules.pop("backend.integrations.fixtures.synthetic_data", None)

    with pytest.raises(ConfigurationError) as exc_info:
        import backend.integrations.fixtures.synthetic_data
    assert "Synthetic fixtures are forbidden" in str(exc_info.value)


def test_report_agent_in_production_returns_no_synthetic_data(enterprise_user, mock_report_service, monkeypatch):
    """In production mode, ReportAgent must not return hardcoded or synthetic fallback data."""
    patch_settings(monkeypatch, app_mode="production")

    # Empty company data service and no database records
    agent = ReportAgent(report_service=mock_report_service, company_data_service=None, database_tool=None)
    req = AgentRequest(request_id="req-1", user=enterprise_user, query="Generate overdue invoices report")
    resp = agent.run(req)

    # Must return clear rejection message without fabricating data
    assert "No verified records found in company documents or database" in resp.content
    assert resp.data_source == "live"
    assert "INV-2026-001" not in resp.content
    assert "Acme Corporation" not in resp.content


def test_report_agent_in_dev_labels_synthetic_data(enterprise_user, mock_report_service, monkeypatch):
    """In dev/demo mode, ReportAgent fallback uses fixtures and marks data_source='synthetic'."""
    patch_settings(monkeypatch, app_mode="development")
    sys.modules.pop("backend.integrations.fixtures.synthetic_data", None)

    agent = ReportAgent(report_service=mock_report_service, company_data_service=None, database_tool=None)
    req = AgentRequest(request_id="req-2", user=enterprise_user, query="Generate overdue invoices report")
    resp = agent.run(req)

    assert resp.data_source == "synthetic"
    assert "INV-2026-003" in resp.content or "INV-2026-005" in resp.content


def test_gmail_provider_raises_dependency_unavailable_in_production(monkeypatch):
    """In production, Gmail search without live credentials must raise DependencyUnavailableError."""
    patch_settings(monkeypatch, app_mode="production")

    provider = GmailEmailProvider()
    ctx = EmailProviderContext(user_id="user-1", tenant_id="tenant-1", access_token="")
    req = EmailSearchRequest(query="financial report")

    with pytest.raises(DependencyUnavailableError) as exc_info:
        provider.search_page(ctx, req)
    assert exc_info.value.dependency == "email"
    assert "No Gmail account is connected" in str(exc_info.value)


def test_email_agent_returns_clear_unconnected_message(enterprise_user, monkeypatch):
    """In production, if no mailbox is connected, EmailAgent must clearly state it and not fake data."""
    patch_settings(monkeypatch, app_mode="production")

    with patch("backend.integrations.email.user_account_service.get_user_email_account_service") as mock_account_svc:
        mock_account_svc.return_value.get_active_account.return_value = None

        mock_email_svc = MagicMock()
        agent = EmailAgent(email_service=mock_email_svc)
        req = AgentRequest(request_id="req-3", user=enterprise_user, query="check my inbox for Q1 financial report")
        resp = agent.run(req)

        assert "No Gmail account is connected" in resp.content
        assert resp.data_source == "live"
        assert "Q1 2026 Financial Results" not in resp.content


def test_sqlite_enterprise_repository_rejected_in_production(monkeypatch):
    """Instantiating SQLiteEnterpriseRepository in production must raise DependencyUnavailableError."""
    patch_settings(monkeypatch, app_mode="production")

    with pytest.raises(DependencyUnavailableError) as exc_info:
        SQLiteEnterpriseRepository()
    assert exc_info.value.dependency == "database"
    assert "SQLite fallback is forbidden in production" in str(exc_info.value)
