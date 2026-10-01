"""Tests for Milestone 6: Centralized Intent and Action Registry.

Tests:
1. Intent registration and metadata validation
2. Role-based permission checks (RBAC)
3. Dynamic contextual action selection
4. High-risk intent safety confirmation enforcement (Section 12)
5. Intent execution through the unified orchestration pipeline
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

from backend.chat.intent_registry import (
    IntentDefinition,
    IntentRegistry,
    RiskLevel,
    intent_registry,
)
from backend.security.authorization.abac import UserAttributes
from backend.security.authorization.rbac import Role


@pytest.fixture
def ceo_user():
    return UserAttributes(
        user_id="user_ceo",
        tenant_id="tenant_nanvi",
        department="Executive",
        roles=frozenset({Role.CEO}),
    )


@pytest.fixture
def finance_user():
    return UserAttributes(
        user_id="user_fin",
        tenant_id="tenant_nanvi",
        department="Finance",
        roles=frozenset({Role.FINANCE}),
    )


@pytest.fixture
def employee_user():
    return UserAttributes(
        user_id="user_emp",
        tenant_id="tenant_nanvi",
        department="Engineering",
        roles=frozenset({Role.EMPLOYEE}),
    )


class TestIntentRegistryCore:
    def test_default_intents_registered(self):
        assert intent_registry.get("compare_previous_quarter") is not None
        assert intent_registry.get("revenue_drivers") is not None
        assert intent_registry.get("customer_invoices") is not None
        assert intent_registry.get("send_confirmation") is not None
        assert intent_registry.get("verify_sources") is not None

    def test_rbac_permission_check(self, ceo_user, finance_user, employee_user):
        # Finance and CEO can access financial comparison
        assert intent_registry.can_execute(ceo_user, "compare_previous_quarter") is True
        assert intent_registry.can_execute(finance_user, "compare_previous_quarter") is True

        # Regular employee cannot access restricted finance comparison
        assert intent_registry.can_execute(employee_user, "compare_previous_quarter") is False

        # All employees can access general search and source verification
        assert intent_registry.can_execute(employee_user, "verify_sources") is True
        assert intent_registry.can_execute(employee_user, "show_more_detail") is True

    def test_resolve_query_template(self):
        intent = intent_registry.get("compare_previous_quarter")
        assert intent is not None
        query = intent.resolve_query()
        assert "quarter" in query.lower()

        # Custom interpolation
        custom_intent = IntentDefinition(
            intent_id="view_customer_report",
            label="View Customer",
            description="View account",
            category="crm",
            query_template="Show details for customer {customer_id}",
        )
        assert custom_intent.resolve_query({"customer_id": "CUST-015"}) == "Show details for customer CUST-015"

    def test_contextual_action_selection(self, employee_user, finance_user):
        # Finance user gets financial actions
        fin_actions = intent_registry.get_actions_for_context(
            user=finance_user,
            suggested_intents=["compare_previous_quarter", "revenue_drivers"],
            capability="database",
            limit=3,
        )
        action_ids = [a.intent_id for a in fin_actions]
        assert "compare_previous_quarter" in action_ids
        assert "revenue_drivers" in action_ids

        # Employee user filters out restricted finance actions and falls back to safe actions
        emp_actions = intent_registry.get_actions_for_context(
            user=employee_user,
            suggested_intents=["compare_previous_quarter"],
            capability="knowledge",
            limit=3,
        )
        emp_action_ids = [a.intent_id for a in emp_actions]
        assert "compare_previous_quarter" not in emp_action_ids
        assert any(a in emp_action_ids for a in ("show_more_detail", "verify_sources", "export_summary"))


class TestIntentExecutionEndpoint:
    @pytest.mark.anyio
    async def test_high_risk_intent_requires_confirmation(self, ceo_user):
        from backend.api.voice_routes import execute_voice_intent, ExecuteIntentBody

        body = ExecuteIntentBody(
            intent_id="send_confirmation",
            confirmed=False,
        )
        mock_service = MagicMock()

        result = execute_voice_intent(body=body, user=ceo_user, service=mock_service)
        assert result.get("status") == "confirmation_required"
        assert result.get("intent_id") == "send_confirmation"
        assert result.get("risk_level") == "high"

    @pytest.mark.anyio
    async def test_unauthorized_user_raises_403(self, employee_user):
        from backend.api.voice_routes import execute_voice_intent, ExecuteIntentBody
        from fastapi import HTTPException

        body = ExecuteIntentBody(
            intent_id="compare_previous_quarter",
            confirmed=True,
        )
        mock_service = MagicMock()

        with pytest.raises(HTTPException) as exc:
            execute_voice_intent(body=body, user=employee_user, service=mock_service)
        assert exc.value.status_code == 403

    @pytest.mark.anyio
    async def test_unknown_intent_raises_404(self, ceo_user):
        from backend.api.voice_routes import execute_voice_intent, ExecuteIntentBody
        from fastapi import HTTPException

        body = ExecuteIntentBody(
            intent_id="non_existent_action_xyz",
        )
        mock_service = MagicMock()

        with pytest.raises(HTTPException) as exc:
            execute_voice_intent(body=body, user=ceo_user, service=mock_service)
        assert exc.value.status_code == 404
