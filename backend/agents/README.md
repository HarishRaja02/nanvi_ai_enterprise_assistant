# Agents and Orchestration

Canonical documentation: [`../../docs/02-architecture.md`](../../docs/02-architecture.md), [`../../docs/10-tool-gateway.md`](../../docs/10-tool-gateway.md).

Implemented: LangGraph graph shell, deterministic router, LLM-router interface, agent contracts, orchestration state and SecureToolGateway.

Partial: only `DatabaseAgent` has a concrete `run()` implementation when a DatabaseTool/planner are injected. Knowledge, Email, DataAnalysis and Report agent classes remain capability shells. The default FastAPI chat dependency is not configured.

Future: concrete agent wiring and live model/provider integration.
