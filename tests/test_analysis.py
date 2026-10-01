from backend.analysis import (
    AnalysisOperation, AnalysisRequest, DataLineage, DeterministicAnalysisEngine,
    StructuredDataset, dataset_from_query_result,
)
from backend.integrations.database.models import QueryResult
import pytest


@pytest.fixture
def dataset():
    rows = (
        {"month": "2026-08", "customer": "A", "sales": 10000, "status": "paid"},
        {"month": "2026-08", "customer": "B", "sales": 15000, "status": "overdue"},
        {"month": "2026-09", "customer": "A", "sales": 12000, "status": "paid"},
        {"month": "2026-09", "customer": "B", "sales": 20000, "status": "overdue"},
    )
    return StructuredDataset(tuple(rows[0].keys()), rows, (DataLineage("sql", "sales", "sales", tuple(rows[0].keys()), "SELECT ..."),))


def test_total_and_lineage(dataset):
    result = DeterministicAnalysisEngine().execute(AnalysisRequest(AnalysisOperation.TOTAL, dataset, column="sales"))
    assert result.value == 57000
    assert result.lineage[0].source_id == "sales"


def test_compare_periods(dataset):
    result = DeterministicAnalysisEngine().execute(AnalysisRequest(
        AnalysisOperation.COMPARE, dataset, column="sales", period_column="month",
        current_period="2026-09", previous_period="2026-08"))
    assert result.value["current"] == 32000
    assert result.value["previous"] == 25000
    assert result.value["change"] == 7000
    assert result.value["percent_change"] == pytest.approx(28.0)


def test_filter_and_group(dataset):
    engine = DeterministicAnalysisEngine()
    filtered = engine.execute(AnalysisRequest(AnalysisOperation.FILTER, dataset, filter_column="sales", filter_operator=">", filter_value=10000))
    assert len(filtered.value) == 3
    grouped = engine.execute(AnalysisRequest(AnalysisOperation.GROUP, dataset, column="sales", group_by="month"))
    assert grouped.value["2026-09"]["total"] == 32000


def test_trend_and_stats(dataset):
    engine = DeterministicAnalysisEngine()
    trend = engine.execute(AnalysisRequest(AnalysisOperation.TREND, dataset, column="sales", period_column="month"))
    assert trend.value[0]["total"] == 25000
    stats = engine.execute(AnalysisRequest(AnalysisOperation.STATS, dataset, column="sales"))
    assert stats.value["count"] == 4
    assert stats.value["max"] == 20000


def test_sql_result_lineage():
    dataset = dataset_from_query_result(QueryResult(("amount",), ((10,), (20,))), "invoice-db", "SELECT amount FROM invoices")
    assert dataset.rows[1]["amount"] == 20
    assert dataset.lineage[0].source_type == "sql"
    assert dataset.lineage[0].query == "SELECT amount FROM invoices"


def test_invalid_column_rejected(dataset):
    with pytest.raises(ValueError, match="Unknown column"):
        DeterministicAnalysisEngine().execute(AnalysisRequest(AnalysisOperation.TOTAL, dataset, column="secret_salary"))
