from __future__ import annotations
from typing import Any, Callable
from backend.security.audit import AuditLogger
from backend.security.authorization import UserAttributes
from .engine import DeterministicAnalysisEngine
from .models import AnalysisRequest, AnalysisResponse


class AnalysisExplanationProvider:
    """Optional LLM boundary: receives calculated results only, never raw unauthorized data."""
    def explain(self, query: str, response: AnalysisResponse) -> str:
        return str(response.result.value)


class DataAnalysisService:
    def __init__(self, engine: DeterministicAnalysisEngine, audit: AuditLogger, explainer: AnalysisExplanationProvider | None = None):
        self._engine = engine
        self._audit = audit
        self._explainer = explainer

    def analyze(self, user: UserAttributes, request_id: str, request: AnalysisRequest, query: str = "") -> AnalysisResponse:
        # Authorization has already occurred at source loading/tool boundary. This service
        # deliberately accepts StructuredDataset, not arbitrary paths or credentials.
        result = self._engine.execute(request)
        response = AnalysisResponse(result=result)
        explanation = self._explainer.explain(query, response) if self._explainer else None
        response = AnalysisResponse(result, explanation)
        self._audit.record("data_analysis", "allow", user.user_id, user.tenant_id, request_id, {
            "operation": request.operation.value, "row_count": result.row_count,
            "sources": [x.source_id for x in result.lineage],
        })
        return response
