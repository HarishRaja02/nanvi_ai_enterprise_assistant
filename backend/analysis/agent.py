from __future__ import annotations
from backend.agents.interfaces import Agent
from backend.agents.models import AgentRequest, AgentResponse, Capability
from backend.security.authorization import Permission, Resource
from backend.sources.service import SourceReferenceService
from backend.agents.security_gateway import SecureToolGateway, ToolContext
from .service import DataAnalysisService
from .models import AnalysisRequest


class DataAnalysisAgent(Agent):
    capability = Capability.DATA_ANALYSIS

    def __init__(self, analysis_service: DataAnalysisService, gateway: SecureToolGateway,
                 source_references: SourceReferenceService | None = None):
        self._service = analysis_service
        self._gateway = gateway
        self._source_references = source_references

    def analyze(self, request: AgentRequest, analysis: AnalysisRequest) -> AgentResponse:
        resource = Resource(resource_id=request.request_id, resource_type="data_analysis", tenant_id=request.user.tenant_id)
        result = self._gateway.execute(
            ToolContext(request.request_id, request.user), "data_analysis", Permission.DATABASE_READ,
            resource, lambda: self._service.analyze(request.user, request.request_id, analysis, request.query)
        )
        sources = (
            self._source_references.from_lineage(request.user, request.request_id, result.result.lineage)
            if self._source_references else ()
        )
        return AgentResponse(self.capability, result, sources)

    def run(self, request: AgentRequest) -> AgentResponse:
        raise ValueError("DataAnalysisAgent requires a structured AnalysisRequest; do not infer executable analysis from raw text here")
