from __future__ import annotations
from typing import Callable

from .capability_agents import KnowledgeAgent, DatabaseAgent, EmailAgent, DataAnalysisAgent, ReportAgent, WebSearchAgent, GoogleDriveAgent
from .interfaces import Agent, Router, RuleBasedRouter
from .models import AgentRequest, OrchestrationState, Capability
from backend.observability.logging import log_event
import logging
import time

logger = logging.getLogger(__name__)


class EnterpriseOrchestrator:
    """LangGraph orchestration shell. Authentication is expected before graph invocation."""
    def __init__(self, router: Router | None = None, agents: dict | None = None):
        self.router = router or RuleBasedRouter()
        self.agents = agents or {
            agent.capability: agent for agent in (
                KnowledgeAgent(), DatabaseAgent(), EmailAgent(), DataAnalysisAgent(), ReportAgent(), WebSearchAgent(), GoogleDriveAgent()
            )
        }
        self.graph = self._build_graph()

    def _build_graph(self):
        try:
            from langgraph.graph import END, START, StateGraph
        except ImportError as exc:
            raise RuntimeError("LangGraph is required to build the orchestration graph") from exc

        all_nodes = ("knowledge", "database", "email", "data_analysis", "report", "web_search", "google_drive")
        builder = StateGraph(OrchestrationState)
        builder.add_node("route", self._route_node)
        for node in all_nodes:
            builder.add_node(node, self._agent_node(node))
        builder.add_edge(START, "route")
        builder.add_conditional_edges("route", lambda state: state.capability.value, {
            node: node for node in all_nodes
        })
        for node in all_nodes:
            builder.add_edge(node, END)
        return builder.compile()

    def _route_node(self, state: OrchestrationState) -> dict:
        started = time.perf_counter()
        capability = state.capability or self.router.route(state.query)
        log_event(logger, "orchestrator_routed", actor_id=state.user_id, tenant_id=state.tenant_id,
                  request_id=state.request_id, capability=capability.value,
                  query_length=len(state.query), duration_ms=round((time.perf_counter() - started) * 1000, 2))
        return {"capability": capability, "trace": [*state.trace, f"route:{capability.value}"]}

    def _agent_node(self, capability_value: str) -> Callable:
        def node(state: OrchestrationState) -> dict:
            capability = next((c for c in self.agents if c.value == capability_value), None)
            if capability is None or capability not in self.agents:
                from .models import AgentResponse
                cap_enum = next((c for c in Capability if c.value == capability_value), Capability.KNOWLEDGE)
                return {
                    "response": AgentResponse(cap_enum, f"{capability_value.replace('_', ' ').title()} service is not configured in this environment.", ()),
                    "trace": [*state.trace, f"agent:{capability_value}:not_configured"]
                }
            # Agent implementations will later call SecureToolGateway. No credential is passed here.
            request = AgentRequest(
                request_id=state.request_id,
                user=self._principal_from_state(state),
                query=state.query,
                history=getattr(state, "history", ()),
            )
            started = time.perf_counter()
            try:
                response = self.agents[capability].run(request)
            except Exception as exc:
                log_event(logger, "orchestrator_agent_failed", logging.ERROR, actor_id=state.user_id,
                          tenant_id=state.tenant_id, request_id=state.request_id, capability=capability_value,
                          duration_ms=round((time.perf_counter() - started) * 1000, 2),
                          exception_type=type(exc).__name__)
                raise
            log_event(logger, "orchestrator_agent_completed", actor_id=state.user_id, tenant_id=state.tenant_id,
                      request_id=state.request_id, capability=capability_value,
                      duration_ms=round((time.perf_counter() - started) * 1000, 2),
                      source_count=len(response.sources))
            return {"response": response, "trace": [*state.trace, f"agent:{capability_value}"]}
        return node

    @staticmethod
    def _principal_from_state(state: OrchestrationState | dict):
        from backend.security.authorization import UserAttributes
        if isinstance(state, dict):
            return UserAttributes(
                user_id=state["user_id"],
                tenant_id=state["tenant_id"],
                department=state.get("department"),
                roles=frozenset(state.get("roles", ())),
            )
        return UserAttributes(
            user_id=state.user_id, tenant_id=state.tenant_id,
            department=state.department, roles=frozenset(state.roles),
        )

    def invoke(self, request: AgentRequest, forced_capability: Capability | None = None) -> OrchestrationState:
        state = OrchestrationState.from_request(request)
        if forced_capability is not None:
            state.capability = forced_capability
        started = time.perf_counter()
        log_event(logger, "orchestrator_started", actor_id=request.user.user_id, tenant_id=request.user.tenant_id,
                  request_id=request.request_id, forced_capability=forced_capability.value if forced_capability else None,
                  query_length=len(request.query))
        try:
            result = self.graph.invoke(state)
        except Exception as exc:
            log_event(logger, "orchestrator_failed", logging.ERROR, actor_id=request.user.user_id,
                      tenant_id=request.user.tenant_id, request_id=request.request_id,
                      duration_ms=round((time.perf_counter() - started) * 1000, 2),
                      exception_type=type(exc).__name__)
            raise
        if isinstance(result, dict):
            import dataclasses
            known = {f.name for f in dataclasses.fields(OrchestrationState)}
            result = OrchestrationState(**{k: v for k, v in result.items() if k in known})
        log_event(logger, "orchestrator_completed", actor_id=request.user.user_id, tenant_id=request.user.tenant_id,
                  request_id=request.request_id, capability=result.capability.value if result.capability else None,
                  duration_ms=round((time.perf_counter() - started) * 1000, 2),
                  trace_steps=len(result.trace))
        return result
