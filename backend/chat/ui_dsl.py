"""Controlled Generative UI DSL — Milestone 5.

Defines the exhaustive set of UI card specifications that the response planner
can emit. The frontend receives these as structured JSON via UI_SPEC SSE events
and renders them into glassmorphism cards.

This is a CONTROLLED vocabulary — the LLM never invents card types. Only the
card types defined in UICardType are valid. This prevents hallucinated UI while
allowing rich, contextual visual presentation.

Implements Section 10 of docs/NANVI_SPEC.md.
"""
from __future__ import annotations

import re
from enum import Enum
from typing import Any, Sequence
from pydantic import BaseModel, Field


class UICardType(str, Enum):
    """Exhaustive set of allowed card types. No other types may be emitted."""
    KPI_CARD = "kpi_card"
    TABLE_CARD = "table_card"
    SOURCE_LIST = "source_list"
    TIMELINE_CARD = "timeline_card"
    STATUS_CARD = "status_card"
    ACTION_CARD = "action_card"


class KPICardData(BaseModel):
    """Hero metric card — single key number with optional trend and comparison."""
    metric_label: str
    value: str
    unit: str = ""
    trend: str = ""  # "up" | "down" | "flat" | ""
    trend_value: str = ""  # e.g. "+14.2%"
    comparison_label: str = ""  # e.g. "vs. last quarter"


class TableColumn(BaseModel):
    key: str
    label: str
    align: str = "left"  # "left" | "right" | "center"


class TableCardData(BaseModel):
    """Structured tabular data card with column definitions and row data."""
    title: str = ""
    columns: list[TableColumn]
    rows: list[dict[str, Any]]
    total_rows: int = 0  # total available (for pagination hint)
    truncated: bool = False


class SourceItem(BaseModel):
    """A single source reference tile."""
    title: str
    reference_id: str = ""
    file_type: str = ""  # "pdf" | "docx" | "xlsx" | "email" | "web" | "db"
    relevance_score: float = 0.0
    snippet: str = ""


class SourceListData(BaseModel):
    """List of verified source references."""
    sources: list[SourceItem]
    query_context: str = ""


class TimelineItem(BaseModel):
    """A single chronological event."""
    timestamp: str
    title: str
    detail: str = ""
    icon: str = ""  # "email" | "file" | "meeting" | "alert" | "milestone"


class TimelineCardData(BaseModel):
    """Chronologically ordered event sequence."""
    title: str = "Timeline"
    items: list[TimelineItem]


class StatusCardData(BaseModel):
    """Process status or confirmation card."""
    status: str  # "success" | "warning" | "error" | "info" | "pending"
    title: str
    detail: str = ""
    icon: str = ""  # optional override icon name


class ActionItem(BaseModel):
    """A single suggested follow-up action."""
    label: str
    intent: str  # machine-readable intent ID
    icon: str = ""  # optional icon name
    variant: str = "secondary"  # "primary" | "secondary" | "ghost"


class ActionCardData(BaseModel):
    """Suggested follow-up action buttons."""
    title: str = "Suggested Actions"
    actions: list[ActionItem]


class UISpec(BaseModel):
    """A single UI card specification. The payload type is determined by card_type."""
    card_type: UICardType
    priority: int = 0  # lower = higher priority (rendered first)
    data: dict[str, Any]

    def validate_data(self) -> bool:
        """Validate that data matches the expected schema for the card_type."""
        try:
            if self.card_type == UICardType.KPI_CARD:
                KPICardData(**self.data)
            elif self.card_type == UICardType.TABLE_CARD:
                TableCardData(**self.data)
            elif self.card_type == UICardType.SOURCE_LIST:
                SourceListData(**self.data)
            elif self.card_type == UICardType.TIMELINE_CARD:
                TimelineCardData(**self.data)
            elif self.card_type == UICardType.STATUS_CARD:
                StatusCardData(**self.data)
            elif self.card_type == UICardType.ACTION_CARD:
                ActionCardData(**self.data)
            return True
        except Exception:
            return False


def validate_ui_spec(raw_spec: dict[str, Any]) -> UISpec:
    """Validate raw UI specification dictionary against approved schemas.
    
    If card_type is unknown or data fails validation, safely falls back
    to a standard STATUS_CARD (Section 6.3 & Rule 6 of docs/NANVI_SPEC.md).
    """
    try:
        spec = UISpec(**raw_spec)
        if spec.validate_data():
            return spec
    except Exception:
        pass
    # Safe fallback
    return UISpec(
        card_type=UICardType.STATUS_CARD,
        priority=99,
        data=StatusCardData(
            title="Overview",
            status="info",
            message="Content displayed safely.",
        ).model_dump(),
    )


class UISpecBuilder:
    """Deterministic builder that constructs UISpec cards from query intent, answer shape, and sources.

    This builder does NOT rely on the LLM to generate UI. It uses rule-based heuristics
    to determine which card types best present the response.
    """

    @classmethod
    def build_specs(
        cls,
        query: str,
        answer: str,
        capability: str,
        sources: Sequence[Any] = (),
        suggested_actions: Sequence[str] = (),
        highlights: Sequence[str] = (),
    ) -> list[UISpec]:
        """Build a list of UISpec cards based on the response context."""
        specs: list[UISpec] = []

        # 1. KPI Card: If we detect a dominant numeric answer for a metric query
        kpi = cls._try_build_kpi(query, answer, highlights)
        if kpi:
            specs.append(kpi)

        # 2. Table Card: If answer contains structured tabular data
        table = cls._try_build_table(answer)
        if table:
            specs.append(table)

        # 3. Source List: If we have verified sources
        if sources:
            source_spec = cls._build_source_list(sources, query)
            specs.append(source_spec)

        # 4. Timeline Card: If answer contains date-ordered events
        timeline = cls._try_build_timeline(query, answer)
        if timeline:
            specs.append(timeline)

        # 5. Action Card: Always emit suggested actions
        if suggested_actions:
            action_spec = cls._build_action_card(suggested_actions, query)
            specs.append(action_spec)

        # 6. Status Card: For confirmation / status-type responses
        status = cls._try_build_status(answer, capability)
        if status:
            specs.append(status)

        # Sort by priority (lower number = higher priority)
        specs.sort(key=lambda s: s.priority)
        return specs

    @classmethod
    def _try_build_kpi(
        cls,
        query: str,
        answer: str,
        highlights: Sequence[str] = (),
    ) -> UISpec | None:
        """Detect numeric metric answers and build KPI cards."""
        q_lower = query.lower()
        metric_keywords = (
            "revenue", "total", "sales", "count", "average", "profit", "margin",
            "how many", "how much", "what is the", "balance", "amount", "cost",
            "expense", "budget", "forecast", "earning", "compare", "quarter",
        )
        if not any(k in q_lower for k in metric_keywords):
            return None

        # Try to extract the dominant metric from the answer
        # Look for currency amounts first
        currency_match = re.search(
            r"(?:₹|rs\.?|inr|\$|usd)\s*([\d,]+(?:\.\d+)?)\s*(?:crore|lakh|million|billion|thousand|cr|l|m|b|k)?",
            answer,
            re.IGNORECASE,
        )
        pct_match = re.search(r"(\d+(?:\.\d+)?)\s*%", answer)

        if not currency_match and not pct_match and not highlights:
            return None

        # Derive the metric label from the query
        label = cls._derive_metric_label(query)

        if currency_match:
            value = currency_match.group(0).strip()
        elif pct_match:
            value = pct_match.group(0).strip()
        elif highlights:
            value = highlights[0]
        else:
            return None

        # Detect trend direction
        trend = ""
        trend_value = ""
        if re.search(r"\b(?:increase|increased|grew|growth|up|higher|risen|rose)\b", answer, re.IGNORECASE):
            trend = "up"
        elif re.search(r"\b(?:decrease|decreased|fell|decline|down|lower|dropped)\b", answer, re.IGNORECASE):
            trend = "down"

        trend_pct = re.search(r"(?:by|of)\s+(\d+(?:\.\d+)?)\s*%", answer, re.IGNORECASE)
        if trend_pct:
            sign = "+" if trend == "up" else "-" if trend == "down" else ""
            trend_value = f"{sign}{trend_pct.group(1)}%"

        data = KPICardData(
            metric_label=label,
            value=value,
            trend=trend,
            trend_value=trend_value,
        )
        return UISpec(card_type=UICardType.KPI_CARD, priority=0, data=data.model_dump())

    @classmethod
    def _derive_metric_label(cls, query: str) -> str:
        """Derive a clean metric label from the user query."""
        q = query.strip().rstrip("?!.")
        # Remove question words
        q = re.sub(r"^(?:what is|what are|how many|how much|show me|tell me|get|find|check)\s+(?:the\s+)?",
                    "", q, flags=re.IGNORECASE).strip()
        # Capitalize and truncate
        if q:
            q = q[0].upper() + q[1:]
        if len(q) > 40:
            q = q[:37].rsplit(" ", 1)[0] + "…"
        return q or "Key Metric"

    @classmethod
    def _try_build_table(cls, answer: str) -> UISpec | None:
        """Detect markdown tables in the answer and parse into structured TableCardData."""
        # Match markdown table pattern: | header1 | header2 |\n| --- | --- |\n| val1 | val2 |
        table_match = re.search(
            r"(\|[^\n]+\|\n\|[\s\-:|]+\|\n(?:\|[^\n]+\|\n?)+)",
            answer,
        )
        if not table_match:
            return None

        table_text = table_match.group(1).strip()
        lines = [l.strip() for l in table_text.split("\n") if l.strip()]

        if len(lines) < 3:
            return None

        # Parse headers
        header_cells = [c.strip() for c in lines[0].split("|") if c.strip()]
        # Skip separator line (line 1)
        # Parse data rows
        rows: list[dict[str, Any]] = []
        for row_line in lines[2:]:
            cells = [c.strip() for c in row_line.split("|") if c.strip()]
            if len(cells) == len(header_cells):
                row_dict = {}
                for idx, header in enumerate(header_cells):
                    row_dict[header] = cells[idx]
                rows.append(row_dict)

        if not rows:
            return None

        columns = [
            TableColumn(key=h, label=h, align="right" if cls._is_numeric_column(rows, h) else "left")
            for h in header_cells
        ]

        data = TableCardData(
            columns=columns,
            rows=rows[:10],  # max 10 preview rows
            total_rows=len(rows),
            truncated=len(rows) > 10,
        )
        return UISpec(card_type=UICardType.TABLE_CARD, priority=1, data=data.model_dump())

    @classmethod
    def _is_numeric_column(cls, rows: list[dict[str, Any]], key: str) -> bool:
        """Check if a column is predominantly numeric."""
        numeric_count = 0
        for row in rows:
            val = str(row.get(key, "")).strip()
            if re.match(r"^[\$₹€]?\s*[\d,.]+%?$", val):
                numeric_count += 1
        return numeric_count > len(rows) / 2

    @classmethod
    def _build_source_list(cls, sources: Sequence[Any], query: str) -> UISpec:
        """Build a source list card from verified sources."""
        items: list[dict[str, Any]] = []
        for src in sources:
            src_dict = src.to_frontend_dict() if hasattr(src, "to_frontend_dict") else getattr(src, "__dict__", {})
            file_type = ""
            filename = src_dict.get("filename", src_dict.get("title", ""))
            if filename:
                ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
                file_type = ext if ext in ("pdf", "docx", "xlsx", "csv", "txt") else ""
            if src_dict.get("capability") == "email":
                file_type = "email"
            elif src_dict.get("capability") == "web_search":
                file_type = "web"
            elif src_dict.get("capability") == "database":
                file_type = "db"

            items.append(SourceItem(
                title=filename or src_dict.get("reference_id", "Source"),
                reference_id=src_dict.get("reference_id", ""),
                file_type=file_type,
                relevance_score=src_dict.get("relevance_score", src_dict.get("score", 0.0)),
                snippet=src_dict.get("snippet", src_dict.get("context_snippet", ""))[:150],
            ).model_dump())

        data = SourceListData(
            sources=items,
            query_context=query[:100],
        )
        return UISpec(card_type=UICardType.SOURCE_LIST, priority=2, data=data.model_dump())

    @classmethod
    def _try_build_timeline(cls, query: str, answer: str) -> UISpec | None:
        """Detect chronologically ordered data in answers (emails, events, milestones)."""
        q_lower = query.lower()
        timeline_keywords = ("timeline", "history", "chronolog", "when did", "sequence", "schedule")
        has_dates = bool(re.findall(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b|\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\s+\d{1,2}", answer))

        if not any(k in q_lower for k in timeline_keywords) and not has_dates:
            return None

        # Extract date-prefixed lines
        date_lines = re.findall(
            r"(\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b|\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\s+\d{1,2}(?:,?\s*\d{4})?)\s*[-:–]?\s*(.+)",
            answer,
        )
        if len(date_lines) < 2:
            return None

        items: list[dict[str, Any]] = []
        for timestamp, detail in date_lines[:8]:
            items.append(TimelineItem(
                timestamp=timestamp.strip(),
                title=detail.strip()[:80],
                icon="milestone",
            ).model_dump())

        data = TimelineCardData(title="Timeline", items=items)
        return UISpec(card_type=UICardType.TIMELINE_CARD, priority=1, data=data.model_dump())

    @classmethod
    def _build_action_card(cls, suggested_actions: Sequence[str], query: str) -> UISpec:
        """Build an action card from suggested action intents via centralized intent registry."""
        from backend.chat.intent_registry import intent_registry

        items: list[dict[str, Any]] = []
        for idx, intent_id in enumerate(suggested_actions[:4]):
            defn = intent_registry.get(intent_id)
            if defn:
                items.append(ActionItem(
                    label=defn.label,
                    intent=defn.intent_id,
                    icon=defn.icon,
                    variant="primary" if idx == 0 else defn.variant,
                ).model_dump())
            else:
                items.append(ActionItem(
                    label=intent_id.replace("_", " ").title(),
                    intent=intent_id,
                    icon="arrow-right",
                    variant="primary" if idx == 0 else "secondary",
                ).model_dump())

        data = ActionCardData(title="What's Next?", actions=items)
        return UISpec(card_type=UICardType.ACTION_CARD, priority=5, data=data.model_dump())

    @classmethod
    def _try_build_status(cls, answer: str, capability: str) -> UISpec | None:
        """Build a status card for confirmation or process results."""
        a_lower = answer.lower()
        if any(k in a_lower for k in ("report has been generated", "report is ready", "exported successfully", "download ready")):
            data = StatusCardData(
                status="success",
                title="Report Generated Successfully",
                detail="Your report is ready for download.",
                icon="check-circle",
            )
            return UISpec(card_type=UICardType.STATUS_CARD, priority=0, data=data.model_dump())

        if any(k in a_lower for k in ("permission denied", "not authorized", "access denied", "do not have permission")):
            data = StatusCardData(
                status="warning",
                title="Access Restricted",
                detail="You don't have permission to access this resource.",
                icon="shield-alert",
            )
            return UISpec(card_type=UICardType.STATUS_CARD, priority=0, data=data.model_dump())

        if any(k in a_lower for k in ("error occurred", "failed to", "could not")):
            data = StatusCardData(
                status="error",
                title="Operation Could Not Complete",
                detail="An issue occurred while processing your request.",
                icon="alert-triangle",
            )
            return UISpec(card_type=UICardType.STATUS_CARD, priority=0, data=data.model_dump())

        return None
