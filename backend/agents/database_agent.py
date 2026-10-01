"""DatabaseAgent implementation with planner injection and SQL read-only validation."""
from __future__ import annotations

import logging
import re
from typing import Protocol

from backend.agents.interfaces import Agent
from backend.agents.models import AgentRequest, AgentResponse, Capability
from backend.agents.security_gateway import SecureToolGateway, ToolContext
from backend.integrations.database import DatabaseTool, QueryResult, SQLValidationError
from backend.observability.logging import log_event
from backend.security.authorization import Permission, Resource, UserAttributes
from backend.sources.models import SourceReference
from backend.sources.service import SourceReferenceService

logger = logging.getLogger(__name__)


class DatabaseQueryPlanner(Protocol):
    def plan(self, question: str, user: UserAttributes) -> tuple[str, tuple]:
        """Return parameterized, read-only SQL. The planner has no DB credentials."""
        ...


class DatabaseAgent(Agent):
    capability = Capability.DATABASE

    def __init__(
        self,
        tool: DatabaseTool | None = None,
        planner: DatabaseQueryPlanner | None = None,
        sources: SourceReferenceService | None = None,
        gateway: SecureToolGateway | None = None,
    ):
        self._tool = tool
        self._planner = planner
        self._sources = sources
        self._gateway = gateway

    def run(self, request: AgentRequest) -> AgentResponse:
        if self._tool is None:
            return AgentResponse(
                self.capability,
                "Database service is not configured for this environment.",
                (),
            )

        if self._planner is None:
            return AgentResponse(
                self.capability,
                "Database query planning is not configured for this environment.",
                (),
            )

        try:
            sql, parameters = self._planner.plan(request.query, request.user)
        except Exception as exc:
            log_event(
                logger,
                "database_agent_plan_failed",
                logging.ERROR,
                actor_id=request.user.user_id,
                tenant_id=request.user.tenant_id,
                exception_type=type(exc).__name__,
            )
            return AgentResponse(
                self.capability,
                "I was unable to formulate a database query for that request.",
                (),
            )

        try:
            if self._gateway is not None:
                context = ToolContext(request_id=request.request_id, user=request.user)
                resource = Resource(
                    resource_id="company-postgresql",
                    resource_type="database_source",
                    tenant_id=request.user.tenant_id,
                )
                result = self._gateway.execute(
                    context,
                    "database",
                    Permission.DATABASE_READ,
                    resource,
                    lambda: self._tool.read(request.user, sql, parameters),
                )
            else:
                result = self._tool.read(request.user, sql, parameters)
        except PermissionError:
            return AgentResponse(
                self.capability,
                "You do not have permission to access this database resource.",
                (),
            )
        except SQLValidationError:
            raise
        except Exception as exc:
            log_event(
                logger,
                "database_agent_query_failed",
                logging.ERROR,
                actor_id=request.user.user_id,
                tenant_id=request.user.tenant_id,
                exception_type=type(exc).__name__,
            )
            return AgentResponse(
                self.capability,
                "The database query could not be completed.",
                (),
            )

        # Format the result into a human-readable markdown response
        table_match = re.search(r"FROM\s+(?:public\.)?(\w+)", sql, re.IGNORECASE)
        table_name = table_match.group(1).title() if table_match else "Records"
        record_count = len(result.rows)

        if not result.rows:
            content = "No matching records found in the database."
        else:
            content = (
                f"Found **{record_count}** record{'s' if record_count != 1 else ''} "
                f"in the `{table_name}` table:\n\n"
                f"{result.to_markdown()}"
            )

        refs: tuple[SourceReference, ...] = ()
        if self._sources is not None and result.rows:
            from backend.analysis.models import DataLineage

            table_label = f"Database: {table_name}"
            lineage = DataLineage(
                source_type="database",
                source_id=f"db-{table_name.lower()}",
                source_label=table_label,
                columns=result.columns,
                query=sql,
                tenant_id=request.user.tenant_id,
                resource_type="database_source",
            )
            refs = self._sources.from_lineage(request.user, request.request_id, (lineage,))

        return AgentResponse(self.capability, content, refs)
