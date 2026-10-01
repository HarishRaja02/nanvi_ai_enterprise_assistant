from __future__ import annotations
from backend.integrations.database.models import QueryResult
from .models import DataLineage, StructuredDataset


def dataset_from_query_result(result: QueryResult, source_id: str, query: str, source_label: str | None = None, *, tenant_id: str | None = None, department: str | None = None, restricted_department: str | None = None) -> StructuredDataset:
    """Convert an already-authorized SQL result into the analysis input model."""
    columns = tuple(result.columns)
    rows = tuple(dict(zip(columns, row)) for row in result.rows)
    lineage = DataLineage("sql", source_id, source_label or "Database", columns, query=query, tenant_id=tenant_id, department=department, restricted_department=restricted_department, resource_type="database_source")
    return StructuredDataset(columns, rows, (lineage,))
