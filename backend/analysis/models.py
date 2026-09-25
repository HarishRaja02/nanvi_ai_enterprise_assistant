from __future__ import annotations
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from backend.security.authorization import UserAttributes


class AnalysisOperation(StrEnum):
    TOTAL = "total"
    AVERAGE = "average"
    COUNT = "count"
    COMPARE = "compare"
    TREND = "trend"
    FILTER = "filter"
    GROUP = "group"
    STATS = "stats"


@dataclass(frozen=True)
class DataLineage:
    source_type: str
    source_id: str
    source_label: str
    columns: tuple[str, ...] = ()
    query: str | None = None
    filters: tuple[str, ...] = ()
    # Authorization context used only by the source-transparency boundary.
    # These fields are never exposed directly to the frontend citation.
    tenant_id: str | None = None
    owner_id: str | None = None
    department: str | None = None
    restricted_department: str | None = None
    resource_type: str | None = None


@dataclass(frozen=True)
class StructuredDataset:
    columns: tuple[str, ...]
    rows: tuple[dict[str, Any], ...]
    lineage: tuple[DataLineage, ...]


@dataclass(frozen=True)
class AnalysisRequest:
    operation: AnalysisOperation
    dataset: StructuredDataset
    column: str | None = None
    group_by: str | None = None
    filter_column: str | None = None
    filter_operator: str | None = None
    filter_value: Any = None
    period_column: str | None = None
    current_period: Any = None
    previous_period: Any = None
    limit: int = 1000


@dataclass(frozen=True)
class AnalysisResult:
    operation: AnalysisOperation
    value: Any
    row_count: int
    lineage: tuple[DataLineage, ...]
    notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class AnalysisResponse:
    result: AnalysisResult
    explanation: str | None = None


@dataclass(frozen=True)
class AnalysisContext:
    request_id: str
    user: UserAttributes
