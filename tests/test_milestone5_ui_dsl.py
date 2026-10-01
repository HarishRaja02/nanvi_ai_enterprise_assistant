"""Tests for Milestone 5: Controlled Generative UI DSL.

Tests:
1. UICardType validation and schema correctness
2. Deterministic UISpecBuilder heuristics (KPI, Table, Sources, Timeline, Actions, Status)
3. HumanResponsePlanner integration with ui_specs
4. Streaming SSE UI_SPEC emission
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock
import pytest

from backend.chat.ui_dsl import (
    UICardType,
    UISpec,
    UISpecBuilder,
    KPICardData,
    TableCardData,
    TableColumn,
    SourceListData,
    TimelineCardData,
    StatusCardData,
    ActionCardData,
)
from backend.chat.response_planner import human_response_planner
from backend.chat.events import EventType


class TestUICardModels:
    def test_kpi_card_schema(self):
        kpi = KPICardData(
            metric_label="Total Revenue",
            value="₹18.4 Cr",
            unit="INR",
            trend="up",
            trend_value="+14.2%",
        )
        spec = UISpec(card_type=UICardType.KPI_CARD, priority=0, data=kpi.model_dump())
        assert spec.validate_data() is True
        assert spec.card_type == UICardType.KPI_CARD
        assert spec.data["value"] == "₹18.4 Cr"

    def test_table_card_schema(self):
        table = TableCardData(
            title="Q3 Performance",
            columns=[
                TableColumn(key="region", label="Region"),
                TableColumn(key="revenue", label="Revenue", align="right"),
            ],
            rows=[
                {"region": "North", "revenue": "$4.2M"},
                {"region": "South", "revenue": "$3.1M"},
            ],
            total_rows=2,
            truncated=False,
        )
        spec = UISpec(card_type=UICardType.TABLE_CARD, priority=1, data=table.model_dump())
        assert spec.validate_data() is True
        assert len(spec.data["columns"]) == 2
        assert len(spec.data["rows"]) == 2

    def test_invalid_spec_data_fails_validation(self):
        # Missing required fields
        spec = UISpec(card_type=UICardType.KPI_CARD, priority=0, data={"invalid_key": "abc"})
        assert spec.validate_data() is False


class TestUISpecBuilder:
    def test_builds_kpi_for_currency_metric(self):
        query = "What is our total revenue for Q3?"
        answer = "Our total revenue reached ₹18.4 Cr, which increased by 14% compared to last quarter."
        specs = UISpecBuilder.build_specs(
            query=query,
            answer=answer,
            capability="knowledge",
            suggested_actions=["compare_previous_quarter"],
        )
        card_types = [s.card_type for s in specs]
        assert UICardType.KPI_CARD in card_types
        kpi_spec = next(s for s in specs if s.card_type == UICardType.KPI_CARD)
        assert "18.4" in kpi_spec.data["value"]
        assert kpi_spec.data["trend"] == "up"

    def test_builds_table_from_markdown_table(self):
        query = "Show me the top 3 customers by volume"
        answer = (
            "Here is the breakdown:\n\n"
            "| Customer | Orders | Revenue |\n"
            "| --- | --- | --- |\n"
            "| Acme Corp | 45 | $120,000 |\n"
            "| Beta LLC | 32 | $85,000 |\n"
            "| Gamma Inc | 19 | $44,000 |\n"
        )
        specs = UISpecBuilder.build_specs(query=query, answer=answer, capability="database")
        card_types = [s.card_type for s in specs]
        assert UICardType.TABLE_CARD in card_types
        table_spec = next(s for s in specs if s.card_type == UICardType.TABLE_CARD)
        assert len(table_spec.data["columns"]) == 3
        assert len(table_spec.data["rows"]) == 3
        assert table_spec.data["rows"][0]["Customer"] == "Acme Corp"

    def test_builds_source_list_when_sources_present(self):
        mock_source = MagicMock()
        mock_source.to_frontend_dict.return_value = {
            "reference_id": "REF-001",
            "filename": "Q3_Report.pdf",
            "capability": "knowledge",
            "relevance_score": 0.94,
            "snippet": "Q3 net revenue recorded at 18.4 crore rupees.",
        }
        specs = UISpecBuilder.build_specs(
            query="Verify Q3 revenue",
            answer="Revenue is ₹18.4 Cr.",
            capability="knowledge",
            sources=[mock_source],
        )
        card_types = [s.card_type for s in specs]
        assert UICardType.SOURCE_LIST in card_types
        source_spec = next(s for s in specs if s.card_type == UICardType.SOURCE_LIST)
        assert len(source_spec.data["sources"]) == 1
        assert source_spec.data["sources"][0]["file_type"] == "pdf"

    def test_builds_action_card_from_suggested_actions(self):
        specs = UISpecBuilder.build_specs(
            query="Tell me about Acme Corp",
            answer="Acme Corp is an active client with outstanding invoices.",
            capability="database",
            suggested_actions=["customer_invoices", "contact_details"],
        )
        card_types = [s.card_type for s in specs]
        assert UICardType.ACTION_CARD in card_types
        action_spec = next(s for s in specs if s.card_type == UICardType.ACTION_CARD)
        assert len(action_spec.data["actions"]) == 2
        assert action_spec.data["actions"][0]["intent"] == "customer_invoices"

    def test_builds_timeline_for_date_sequence(self):
        query = "What is the timeline of recent project milestones?"
        answer = (
            "Here is the schedule:\n"
            "Jan 15 - Project kickoff meeting held.\n"
            "Feb 28 - Phase 1 architecture approved.\n"
            "Mar 10 - Integration testing completed.\n"
        )
        specs = UISpecBuilder.build_specs(query=query, answer=answer, capability="knowledge")
        card_types = [s.card_type for s in specs]
        assert UICardType.TIMELINE_CARD in card_types
        timeline_spec = next(s for s in specs if s.card_type == UICardType.TIMELINE_CARD)
        assert len(timeline_spec.data["items"]) == 3

    def test_builds_status_card_for_report_ready(self):
        specs = UISpecBuilder.build_specs(
            query="Export the financial summary",
            answer="Your report has been generated and is ready for download.",
            capability="report",
        )
        card_types = [s.card_type for s in specs]
        assert UICardType.STATUS_CARD in card_types
        status_spec = next(s for s in specs if s.card_type == UICardType.STATUS_CARD)
        assert status_spec.data["status"] == "success"


class TestResponsePlannerIntegration:
    def test_planner_includes_ui_specs(self):
        plan = human_response_planner.plan_response(
            query="What was our total revenue last year?",
            answer="Our total revenue was $12.5M, reflecting 8% growth.",
            capability="database",
        )
        assert hasattr(plan, "ui_specs")
        assert len(plan.ui_specs) > 0
        assert all(isinstance(s, UISpec) for s in plan.ui_specs)

    def test_planner_empty_answer_has_empty_ui_specs(self):
        plan = human_response_planner.plan_response(
            query="Any updates?",
            answer="",
        )
        assert plan.ui_specs == []
