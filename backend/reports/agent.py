from __future__ import annotations

from backend.agents.interfaces import Agent
from backend.agents.models import AgentRequest, AgentResponse, Capability
from backend.agents.security_gateway import SecureToolGateway, ToolContext
from backend.security.authorization import Permission, Resource
from backend.sources.service import SourceReferenceService

from .models import ReportRequest
from .service import ReportService


class ReportAgent(Agent):
    """Coordinates report creation; authorization remains outside the LLM."""
    capability = Capability.REPORT

    def __init__(self, service: ReportService, gateway: SecureToolGateway,
                 source_references: SourceReferenceService | None = None) -> None:
        self._service = service
        self._gateway = gateway
        self._source_references = source_references

    def create(self, request: AgentRequest, report: ReportRequest) -> AgentResponse:
        resource = Resource(resource_id=report.report_id, resource_type="user_report",
                            tenant_id=request.user.tenant_id, owner_id=request.user.user_id)
        artifact = self._gateway.execute(
            ToolContext(request.request_id, request.user),
            "report",
            Permission.REPORT_CREATE,
            resource,
            lambda: self._service.create_report(request.user, report),
        )
        sources = (
            self._source_references.from_lineage(request.user, request.request_id, artifact.metadata.lineage)
            if self._source_references else ()
        )
        return AgentResponse(self.capability, artifact, sources)

    def run(self, request: AgentRequest) -> AgentResponse:
        raise ValueError("ReportAgent requires a structured ReportRequest; do not infer report data or format from raw text")
