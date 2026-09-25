from __future__ import annotations
from collections import defaultdict
from datetime import date, datetime
from math import sqrt
from statistics import mean, median, stdev
from typing import Any, Iterable

from .models import AnalysisOperation, AnalysisRequest, AnalysisResult


class AnalysisValidationError(ValueError):
    pass


class DeterministicAnalysisEngine:
    """Performs arithmetic/statistics in Python; the LLM is not the calculator."""

    def execute(self, request: AnalysisRequest) -> AnalysisResult:
        rows = list(request.dataset.rows)
        if request.limit < 1 or request.limit > 100_000:
            raise AnalysisValidationError("limit must be between 1 and 100000")
        rows = self._filter(rows, request) if request.filter_column else rows
        if len(rows) > request.limit:
            rows = rows[: request.limit]
        op = request.operation
        if op == AnalysisOperation.TOTAL:
            return self._aggregate(request, rows, sum, "total")
        if op == AnalysisOperation.AVERAGE:
            return self._aggregate(request, rows, mean, "average")
        if op == AnalysisOperation.COUNT:
            return self._result(request, len(rows), rows)
        if op == AnalysisOperation.FILTER:
            return self._result(request, rows, rows)
        if op == AnalysisOperation.GROUP:
            return self._group(request, rows)
        if op == AnalysisOperation.COMPARE:
            return self._compare(request, rows)
        if op == AnalysisOperation.TREND:
            return self._trend(request, rows)
        if op == AnalysisOperation.STATS:
            return self._stats(request, rows)
        raise AnalysisValidationError(f"Unsupported analysis operation: {op}")

    def _aggregate(self, request, rows, fn, label):
        values = self._numeric(rows, request.column)
        if not values:
            raise AnalysisValidationError("No numeric values available for the requested column")
        return self._result(request, fn(values), rows, (f"{label} calculated from {len(values)} numeric values",))

    def _group(self, request, rows):
        self._require_column(request.group_by, rows)
        groups: dict[Any, list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            groups[row.get(request.group_by)].append(row)
        value = {}
        for key, group_rows in groups.items():
            if request.column:
                nums = self._numeric(group_rows, request.column)
                value[key] = {"count": len(group_rows), "total": sum(nums), "average": mean(nums) if nums else None}
            else:
                value[key] = {"count": len(group_rows)}
        return self._result(request, value, rows)

    def _compare(self, request, rows):
        self._require_column(request.period_column, rows)
        self._require_column(request.column, rows)
        if request.current_period is None or request.previous_period is None:
            raise AnalysisValidationError("current_period and previous_period are required for comparison")
        current = self._numeric([r for r in rows if r.get(request.period_column) == request.current_period], request.column)
        previous = self._numeric([r for r in rows if r.get(request.period_column) == request.previous_period], request.column)
        current_value, previous_value = sum(current), sum(previous)
        change = current_value - previous_value
        pct = (change / previous_value * 100) if previous_value else None
        return self._result(request, {"current": current_value, "previous": previous_value, "change": change, "percent_change": pct}, rows)

    def _trend(self, request, rows):
        self._require_column(request.period_column, rows)
        self._require_column(request.column, rows)
        buckets: dict[Any, list[float]] = defaultdict(list)
        for row in rows:
            value = self._number(row.get(request.column))
            if value is not None:
                buckets[row.get(request.period_column)].append(value)
        trend = [{"period": p, "total": sum(v), "average": mean(v), "count": len(v)} for p, v in sorted(buckets.items(), key=lambda x: str(x[0]))]
        return self._result(request, trend, rows)

    def _stats(self, request, rows):
        values = self._numeric(rows, request.column)
        if not values:
            raise AnalysisValidationError("No numeric values available for the requested column")
        return self._result(request, {"count": len(values), "sum": sum(values), "mean": mean(values), "median": median(values), "min": min(values), "max": max(values), "stdev": stdev(values) if len(values) > 1 else 0.0}, rows)

    def _filter(self, rows, request):
        self._require_column(request.filter_column, rows)
        allowed = {"=", "==", "!=", ">", ">=", "<", "<=", "contains"}
        if request.filter_operator not in allowed:
            raise AnalysisValidationError("Unsupported filter operator")
        out = []
        for row in rows:
            left = row.get(request.filter_column)
            right = request.filter_value
            try:
                if request.filter_operator in {"=", "=="}: ok = left == right
                elif request.filter_operator == "!=": ok = left != right
                elif request.filter_operator == ">": ok = left > right
                elif request.filter_operator == ">=": ok = left >= right
                elif request.filter_operator == "<": ok = left < right
                elif request.filter_operator == "<=": ok = left <= right
                else: ok = str(right).casefold() in str(left).casefold()
            except TypeError as exc:
                raise AnalysisValidationError("Filter values have incompatible types") from exc
            if ok: out.append(row)
        return out

    @staticmethod
    def _number(value):
        if value is None or isinstance(value, bool): return None
        try: return float(value)
        except (TypeError, ValueError): return None

    def _numeric(self, rows, column):
        self._require_column(column, rows)
        return [n for n in (self._number(r.get(column)) for r in rows) if n is not None]

    @staticmethod
    def _require_column(column, rows):
        if not column: raise AnalysisValidationError("A required column was not supplied")
        if rows and column not in rows[0]: raise AnalysisValidationError(f"Unknown column: {column}")

    @staticmethod
    def _result(request, value, rows, notes=()):
        return AnalysisResult(request.operation, value, len(rows), request.dataset.lineage, tuple(notes))
