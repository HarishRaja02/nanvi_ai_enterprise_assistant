"""DataAnalysisAgent implementation for structured numerical calculations and analytics."""
from __future__ import annotations

import logging
from typing import Any

from backend.agents.interfaces import Agent
from backend.agents.models import AgentRequest, AgentResponse, Capability
from backend.agents.security_gateway import SecureToolGateway
from backend.observability.logging import log_event
from backend.sources.models import SourceReference
from backend.sources.service import SourceReferenceService

logger = logging.getLogger(__name__)


class DataAnalysisAgent(Agent):
    capability = Capability.DATA_ANALYSIS

    def __init__(
        self,
        analysis_engine=None,
        source_references: SourceReferenceService | None = None,
        gateway: SecureToolGateway | None = None,
        database_tool=None,
        company_data_service=None,
    ):
        self._engine = analysis_engine
        self._sources = source_references
        self._gateway = gateway
        self._database_tool = database_tool
        self._company_data = company_data_service

    def run(self, request: AgentRequest) -> AgentResponse:
        if self._engine is None:
            return AgentResponse(
                self.capability,
                "Data analysis engine is not configured for this environment.",
                (),
            )

        from backend.analysis.models import (
            AnalysisOperation,
            AnalysisRequest,
            DataLineage,
            StructuredDataset,
        )

        query_lower = request.query.casefold()

        # 1. Determine operation
        op = AnalysisOperation.TOTAL
        if any(w in query_lower for w in ("average", "mean", "avg")):
            op = AnalysisOperation.AVERAGE
        elif any(w in query_lower for w in ("count", "number of", "how many")):
            op = AnalysisOperation.COUNT
        elif "median" in query_lower:
            op = AnalysisOperation.MEDIAN
        elif any(w in query_lower for w in ("min", "minimum", "lowest")):
            op = AnalysisOperation.MIN
        elif any(w in query_lower for w in ("max", "maximum", "highest")):
            op = AnalysisOperation.MAX

        # 2. Fetch structured data from database tool
        dataset = None
        target_column = None

        if self._database_tool is not None:
            try:
                if any(w in query_lower for w in ("salary", "salaries", "compensation", "payroll", "employee", "staff")):
                    res = self._database_tool.read(request.user, "SELECT id, name, department, role, salary FROM public.employees LIMIT 100")
                    target_column = "salary"
                    rows = tuple(dict(zip(res.columns, row)) for row in res.rows)
                    lineage = DataLineage("database", "company-postgresql", "Employees database", res.columns, "SELECT id, name, department, role, salary FROM public.employees LIMIT 100", tenant_id=request.user.tenant_id, resource_type="database_source")
                    dataset = StructuredDataset(res.columns, rows, (lineage,))
                elif any(w in query_lower for w in ("invoice", "invoices", "billing", "unpaid", "overdue")):
                    res = self._database_tool.read(request.user, "SELECT id, customer, amount, status, due_date FROM public.invoices LIMIT 100")
                    target_column = "amount"
                    rows = tuple(dict(zip(res.columns, row)) for row in res.rows)
                    lineage = DataLineage("database", "company-postgresql", "Invoices database", res.columns, "SELECT id, customer, amount, status, due_date FROM public.invoices LIMIT 100", tenant_id=request.user.tenant_id, resource_type="database_source")
                    dataset = StructuredDataset(res.columns, rows, (lineage,))
                elif any(w in query_lower for w in ("contract", "contracts", "annual value", "renewal", "arr")):
                    res = self._database_tool.read(request.user, "SELECT id, customer, contract_type, annual_value, renewal_date FROM public.contracts LIMIT 100")
                    target_column = "annual_value"
                    rows = tuple(dict(zip(res.columns, row)) for row in res.rows)
                    lineage = DataLineage("database", "company-postgresql", "Contracts database", res.columns, "SELECT id, customer, contract_type, annual_value, renewal_date FROM public.contracts LIMIT 100", tenant_id=request.user.tenant_id, resource_type="database_source")
                    dataset = StructuredDataset(res.columns, rows, (lineage,))
                elif any(w in query_lower for w in ("budget", "department")):
                    res = self._database_tool.read(request.user, "SELECT id, name, budget, manager FROM public.departments LIMIT 100")
                    target_column = "budget"
                    rows = tuple(dict(zip(res.columns, row)) for row in res.rows)
                    lineage = DataLineage("database", "company-postgresql", "Departments database", res.columns, "SELECT id, name, budget, manager FROM public.departments LIMIT 100", tenant_id=request.user.tenant_id, resource_type="database_source")
                    dataset = StructuredDataset(res.columns, rows, (lineage,))
            except Exception as exc:
                logger.warning("Database query in DataAnalysisAgent failed: %s", exc)

        if dataset is None or not dataset.rows:
            return AgentResponse(
                self.capability,
                "Data analysis requires structured data from a connected database or file source. "
                "You can query: employee salaries (e.g. 'average salary'), invoice totals (e.g. 'total invoice amount'), "
                "or department budgets.",
                (),
            )

        try:
            analysis_request = AnalysisRequest(
                operation=op,
                dataset=dataset,
                column=target_column,
            )
            result = self._engine.execute(analysis_request)
        except Exception as exc:
            log_event(logger, "data_analysis_failed", logging.ERROR, actor_id=request.user.user_id, error=str(exc))
            return AgentResponse(self.capability, f"Could not perform calculation: {exc}", ())

        refs: tuple[SourceReference, ...] = ()
        val_str = f"${result.value:,.2f}" if isinstance(result.value, (int, float)) and any(k in (target_column or "") for k in ("salary", "amount", "budget", "value")) else f"{result.value}"
        explanation = (
            f"### 📊 Analysis Result\n\n"
            f"• **Operation:** {op.value.upper()}\n"
            f"• **Metric Column:** `{target_column}`\n"
            f"• **Calculated Value:** **{val_str}**\n"
            f"• **Sample Size:** {result.row_count} records\n"
        )
        return AgentResponse(self.capability, explanation, refs)
