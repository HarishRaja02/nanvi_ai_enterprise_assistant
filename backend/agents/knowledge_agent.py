"""KnowledgeAgent implementation for document retrieval and enterprise search."""
from __future__ import annotations

import logging
from typing import Any

from backend.agents.interfaces import Agent
from backend.agents.models import AgentRequest, AgentResponse, Capability
from backend.agents.security_gateway import SecureToolGateway, ToolContext
from backend.security.authorization import Permission, Resource
from backend.sources.models import SourceReference, SourceType
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
                    if res.sources and "couldn't find" not in str(res.answer_content).lower():
                        return AgentResponse(self.capability, res.answer_content, tuple(res.sources), deterministic=True)
                except Exception as exc:
                    logger.warning("CompanyData file search failed, falling back: %s", exc)

            try:
                from backend.chat.file_search import execute_file_search
                ans, files, sources = execute_file_search(request.user, request.query, "local", max_results=10)
                if files:
                    return AgentResponse(self.capability, ans, tuple(sources), deterministic=True)
            except Exception as exc:
                logger.debug("Local agent fallback file search error: %s", exc)

        # 2. Content-first search for Knowledge Questions
        company_data_res = None
        if company_data is not None:
            try:
                company_data_res = company_data.search(
                    request.user,
                    request.query,
                    active_document_id=getattr(request, "active_document_id", None),
                )
            except Exception as exc:
                logger.warning("CompanyData search failed, falling back: %s", exc)

        # 3. Query Local Agent files (from user's approved folders)
        local_hits = []
        try:
            from backend.local_agent.service import get_local_agent_service
            local_svc = get_local_agent_service()
            u_id = getattr(request.user, "user_id", None) or getattr(request.user, "subject", "user")
            t_id = getattr(request.user, "tenant_id", "default")
            local_hits = local_svc.search_local_chunks(
                tenant_id=t_id,
                user_id=u_id,
                query=request.query,
                top_k=5,
            )

            # If specific query produced 0 chunk hits, check if user has local files
            if not local_hits:
                local_files = local_svc.get_all_local_files(t_id, u_id)
                if local_files:
                    q_lower = request.query.lower()
                    # If user is asking for folder listing or available documents
                    if any(w in q_lower for w in ("folder", "my file", "my document", "what do i have", "what is in", "contents", "all file", "show files")):
                        from backend.chat.file_search import execute_file_search
                        ans, files, sources = execute_file_search(request.user, request.query, "local", max_results=10)
                        if files:
                            return AgentResponse(self.capability, ans, tuple(sources), deterministic=True)
                    # For general content inquiries / summarization, pull top content chunks from local files
                    local_hits = local_svc.search_local_chunks(
                        tenant_id=t_id,
                        user_id=u_id,
                        query="",
                        top_k=5,
                    )
        except Exception as exc:
            logger.debug("Local agent search check error: %s", exc)

        if local_hits:
            local_sources = []
            local_snippets = []
            for h in local_hits:
                src_ref = SourceReference(
                    reference_id=f"ref-local-{h.chunk_id[:16]}",
                    source_type=SourceType.FILE,
                    display_name=f"[Local] {h.citation}",
                    title=h.filename,
                    location=h.citation,
                    page=h.page,
                    sheet=h.sheet,
                )
                local_sources.append(src_ref)
                local_snippets.append(f"[{h.citation}]\n{h.text}")

            local_text = "\n\n---\n\n".join(local_snippets)

            if company_data_res and company_data_res.answer_content and "couldn't find" not in company_data_res.answer_content.lower():
                combined_content = f"{company_data_res.answer_content}\n\n### Local Computer Documents:\n{local_text}"
                combined_sources = (*company_data_res.sources, *local_sources)
                return AgentResponse(self.capability, combined_content, combined_sources, deterministic=False)
            return AgentResponse(self.capability, local_text, tuple(local_sources), deterministic=False)

        if company_data_res and company_data_res.sources:
            # [LEGACY] is_restricted = "Access Restricted" in company_data_res.answer_content
            # [LEGACY] is_structured = company_data_res.is_exact_match and ("Found the following" in company_data_res.answer_content)
            # [LEGACY] return AgentResponse(self.capability, company_data_res.answer_content, tuple(company_data_res.sources), deterministic=(is_restricted or is_structured))
            # [LEGACY] End legacy raw chunk output.
            is_restricted = "Access Restricted" in getattr(company_data_res, "answer_content", "")
            if is_restricted:
                return AgentResponse(self.capability, company_data_res.answer_content, (), deterministic=True)

            seen = set()
            clean_sources = []
            for s in company_data_res.sources:
                fn = getattr(s, "display_name", None) or getattr(s, "title", "document")
                # Clean prefix like [Finance] invoice_003.pdf -> invoice_003.pdf
                fn_clean = re.sub(r"^\[[^\]]+\]\s*", "", fn)
                if fn_clean not in seen:
                    seen.add(fn_clean)
                    clean_sources.append(s)

            count = len(clean_sources)
            summary = f"Found **{count}** matching document{'s' if count != 1 else ''}:"
            lines = [
                summary,
                "",
                "| File Name | File Path | Action |",
                "| --- | --- | --- |",
            ]
            for s in clean_sources[:10]:
                fn = re.sub(r"^\[[^\]]+\]\s*", "", getattr(s, "display_name", None) or getattr(s, "title", "document"))
                path = getattr(s, "location", fn) or fn
                lines.append(f"| {fn} | `{path}` | [Open]({path}) |")

            return AgentResponse(
                self.capability,
                "\n".join(lines),
                tuple(clean_sources),
                deterministic=True,
            )
        elif company_data_res and company_data_res.answer_content and company_data_res.sources and "couldn't find" not in str(company_data_res.answer_content).lower():
            return AgentResponse(
                self.capability,
                company_data_res.answer_content,
                tuple(company_data_res.sources),
                deterministic=True,
            )
        elif self._retrieval is None:
            return AgentResponse(
                self.capability,
                "I couldn't find sufficiently relevant information in the authorized documents to answer this question.",
                (),
                deterministic=False,
            )

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
