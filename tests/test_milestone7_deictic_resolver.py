"""Tests for Milestone 7: Contextual Follow-ups and Deictic Reference Resolution.

Tests:
1. Causal follow-up ("Why?") resolution against prior query topic
2. Ordinal references ("Open the second one", "customer #2") via ui_entity_index
3. Active document and entity deictic references ("this invoice", "this contract")
4. Elliptical refinements ("Only enterprise", "In Q3")
5. Automatic indexing from table cards and sources into ui_entity_index
6. Multi-turn pipeline integration in ChatService
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from backend.chat.deictic_resolver import DeicticResolver
from backend.chat.context_engine import (
    ConversationContext,
    DocumentContext,
    EntityContext,
    UserContext,
)
from backend.chat.ui_dsl import UISpec, UICardType, TableCardData, TableColumn


@pytest.fixture
def base_context():
    return ConversationContext(
        conversation_id="conv_m7_test",
        user=UserContext(id="test_user", role="CEO"),
        ui_entity_index={
            "1": {"id": "CUST-001", "name": "Acme Corp"},
            "2": {"id": "CUST-002", "name": "Beta Industries"},
            "3": {"id": "CUST-003", "name": "Gamma Global"},
        },
        active_document=DocumentContext(
            document_id="INV-2024-042",
            filename="INV-2024-042_Acme_Invoice.pdf",
        ),
        active_entity=EntityContext(
            type="customer",
            id="CUST-001",
            name="Acme Corp",
        ),
    )


class TestDeicticResolver:
    def test_why_causal_resolution(self):
        prior_q = "What was our total revenue for Q3?"
        prior_a = "Our revenue was ₹18.4 Cr, up 14%."
        resolved = DeicticResolver.resolve(
            query="Why?",
            context=None,
            prior_user_query=prior_q,
            prior_assistant_answer=prior_a,
        )
        assert "revenue" in resolved.lower()
        assert "drivers" in resolved.lower() or "factors" in resolved.lower()
        assert "What was our total revenue for Q3" in resolved

    def test_ordinal_reference_resolution(self, base_context):
        # Test "Open the second one"
        resolved_2nd = DeicticResolver.resolve(
            query="Open the second one",
            context=base_context,
        )
        assert "Beta Industries" in resolved_2nd

        # Test "Show customer #1"
        resolved_1st = DeicticResolver.resolve(
            query="Show customer #1",
            context=base_context,
        )
        assert "Acme Corp" in resolved_1st

        # Test "Check the third one"
        resolved_3rd = DeicticResolver.resolve(
            query="Check the third one",
            context=base_context,
        )
        assert "Gamma Global" in resolved_3rd

    def test_active_document_deictic_reference(self, base_context):
        query = "What is the total amount due on this invoice?"
        resolved = DeicticResolver.resolve(
            query=query,
            context=base_context,
        )
        assert "INV-2024-042_Acme_Invoice.pdf" in resolved

    def test_active_entity_deictic_reference(self, base_context):
        query = "Who is the primary contact for this customer?"
        resolved = DeicticResolver.resolve(
            query=query,
            context=base_context,
        )
        assert "Acme Corp" in resolved

    def test_elliptical_filter_refinement(self):
        prior_q = "Show me the top 10 customers by revenue"
        follow_up = "Only enterprise"
        resolved = DeicticResolver.resolve(
            query=follow_up,
            context=None,
            prior_user_query=prior_q,
        )
        assert "Show me the top 10 customers by revenue" in resolved
        assert "Only enterprise" in resolved

    def test_build_ui_entity_index_from_table(self):
        table_card = UISpec(
            card_type=UICardType.TABLE_CARD,
            priority=1,
            data=TableCardData(
                columns=[
                    TableColumn(key="customer", label="Customer"),
                    TableColumn(key="orders", label="Orders"),
                ],
                rows=[
                    {"customer": "Alpha Ltd", "orders": "120"},
                    {"customer": "Omega Systems", "orders": "85"},
                ],
            ).model_dump(),
        )
        index = DeicticResolver.build_ui_entity_index([table_card])
        assert "1" in index
        assert index["1"]["name"] == "Alpha Ltd"
        assert "2" in index
        assert index["2"]["name"] == "Omega Systems"
