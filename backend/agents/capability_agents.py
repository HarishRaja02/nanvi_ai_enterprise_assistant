"""Fully-wired capability agents using existing services through SecureToolGateway.

Refactored into individual agent modules under backend/agents/:
- KnowledgeAgent -> backend.agents.knowledge_agent
- DatabaseAgent, DatabaseQueryPlanner -> backend.agents.database_agent
- EmailAgent -> backend.agents.email_agent
- DataAnalysisAgent -> backend.agents.analysis_agent
- ReportAgent -> backend.agents.report_agent
- WebSearchAgent, run_web_agent -> backend.agents.web_search_agent
- GoogleDriveAgent -> backend.agents.google_drive_agent
"""
from __future__ import annotations

from backend.agents.interfaces import Agent
from backend.agents.models import AgentRequest, AgentResponse, Capability

from .knowledge_agent import KnowledgeAgent
from .database_agent import DatabaseAgent, DatabaseQueryPlanner
from .email_agent import EmailAgent
from .analysis_agent import DataAnalysisAgent
from .report_agent import ReportAgent
from .web_search_agent import WebSearchAgent, run_web_agent
from .google_drive_agent import GoogleDriveAgent


class BaseCapabilityAgent(Agent):
    """Base with safe error wrapping."""

    def run(self, request: AgentRequest) -> AgentResponse:
        raise NotImplementedError("Capability agent must be wired with its service dependencies")


__all__ = [
    "BaseCapabilityAgent",
    "KnowledgeAgent",
    "DatabaseQueryPlanner",
    "DatabaseAgent",
    "EmailAgent",
    "DataAnalysisAgent",
    "ReportAgent",
    "WebSearchAgent",
    "run_web_agent",
    "GoogleDriveAgent",
]
