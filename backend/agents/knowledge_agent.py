"""KnowledgeAgent implementation for document retrieval and enterprise search."""
from __future__ import annotations

import logging
from typing import Any

from backend.agents.interfaces import Agent
from backend.agents.models import AgentRequest, AgentResponse, Capability
from backend.agents.security_gateway import SecureToolGateway, ToolContext
from backend.security.authorization import Permission, Resource
from backend.sources.models import SourceReference
from backend.sources.service import SourceReferenceService

logger = logging.getLogger(__name__)


class KnowledgeAgent(Agent):
    capability = Capability.KNOWLEDGE

    def __init__(
        self,
        retrieval_service=None,
        source_references: SourceReferenceService | None = None,
        gateway: SecureToolGateway | None = None,
        company_data_service=None,
    ):
        self._retrieval = retrieval_service
        self._sources = source_references
        self._gateway = gateway
        self._company_data = company_data_service

    def run(self, request: AgentRequest) -> AgentResponse:
        from backend.retrieval.intent import classify_retrieval_intent, QueryIntent

        intent = classify_retrieval_intent(request.query)

        company_data = self._company_data
        if hasattr(company_data, "for_tenant") and request.user.tenant_id:
            company_data = company_data.for_tenant(request.user.tenant_id)
        elif company_data is not None and getattr(company_data, "tenant_id", None) != request.user.tenant_id and request.user.tenant_id:
            from backend.integrations.files.company_data_service import CompanyDataService
            company_data = CompanyDataService.for_tenant(request.user.tenant_id)

        # 1. Deterministic File Discovery / Directory Listing (0 Groq calls)
        if intent in (QueryIntent.FILE_SEARCH, QueryIntent.DIRECTORY_LISTING):
            if company_data is not None:
                try:
                    res = company_data.search_files(request.user, request.query)
                    if res.answer_content:
                        return AgentResponse(self.capability, res.answer_content, tuple(res.sources), deterministic=True)
                except Exception as exc:
                    logger.warning("CompanyData file search failed, falling back: %s", exc)

        # 2. Content-first search for Knowledge Questions
        if company_data is not None:
            try:
                res = company_data.search(
                    request.user,
                    request.query,
                    active_document_id=getattr(request, "active_document_id", None),
                )
                if res.answer_content:
                    is_restricted = "Access Restricted" in res.answer_content
                    is_structured = res.is_exact_match and ("Found the following" in res.answer_content)
                    return AgentResponse(
                        self.capability,
                        res.answer_content,
                        tuple(res.sources),
                        deterministic=(is_restricted or is_structured),
                    )
                elif self._retrieval is None:
                    return AgentResponse(
                        self.capability,
                        "I couldn't find sufficiently relevant information in the authorized documents to answer this question.",
                        (),
                        deterministic=True,
                    )
            except Exception as exc:
                logger.warning("CompanyData search failed, falling back: %s", exc)

        if self._retrieval is None:
            return AgentResponse(
                self.capability,
                "Knowledge retrieval is not configured for this environment.",
                (),
            )

        from backend.retrieval.models import RetrievalRequest

        if self._gateway is not None:
            context = ToolContext(request_id=request.request_id, user=request.user)
            resource = Resource(
                resource_id="knowledge-retrieval",
                resource_type="knowledge_source",
                tenant_id=request.user.tenant_id,
            )
            result = self._gateway.execute(
                context,
                "knowledge",
                Permission.FILE_READ,
                resource,
                lambda: self._retrieval.retrieve(
                    request.user,
                    RetrievalRequest(query=request.query, top_k=5, candidate_k=20),
                ),
            )
        else:
            result = self._retrieval.retrieve(
                request.user,
                RetrievalRequest(query=request.query, top_k=5, candidate_k=20),
            )

        if not result.hits:
            return AgentResponse(
                self.capability,
                "I couldn't find sufficiently relevant information in the authorized documents to answer this question.",
                (),
            )

        # Build content from authorized retrieval hits
        content_parts = []
        for hit in result.hits:
            content_parts.append(hit.chunk.content)
        content = "\n\n".join(content_parts)

        # Build source references
        refs: tuple[SourceReference, ...] = ()
        if self._sources:
            refs = self._retrieval.source_references(
                request.user, request.request_id, result
            )

        return AgentResponse(self.capability, content, refs)
