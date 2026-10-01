"""WebSearchAgent implementation for real-time external search and synthesis."""
from __future__ import annotations

import logging
import os
from typing import Any

from backend.agents.interfaces import Agent
from backend.agents.models import AgentRequest, AgentResponse, Capability
from backend.agents.security_gateway import SecureToolGateway, ToolContext
from backend.security.authorization import Permission, Resource
from backend.sources.service import SourceReferenceService

logger = logging.getLogger(__name__)


class WebSearchAgent(Agent):
    capability = Capability.WEB_SEARCH

    def __init__(
        self,
        web_search_service: Any | None = None,
        sources: SourceReferenceService | None = None,
        gateway: SecureToolGateway | None = None,
        llm_provider: Any = None,
    ):
        self._search = web_search_service
        self._sources = sources
        self._gateway = gateway
        self._llm = llm_provider

    def run(self, request: AgentRequest) -> AgentResponse:
        from backend.integrations.web.service import WebSearchService

        search_service = self._search or WebSearchService()
        if not search_service.is_configured:
            return AgentResponse(
                self.capability,
                "Web search is not configured. Set TAVILY_API_KEY in the backend environment.",
                (),
            )

        if self._gateway is not None:
            context = ToolContext(request_id=request.request_id, user=request.user)
            resource = Resource(
                resource_id="web-search",
                resource_type="web_source",
                tenant_id=request.user.tenant_id,
            )
            results = self._gateway.execute(
                context,
                "web_search",
                Permission.WEB_SEARCH,
                resource,
                lambda: search_service.search(request.query, max_results=5),
            )
        else:
            results = search_service.search(request.query, max_results=5)

        if not results:
            return AgentResponse(
                self.capability,
                f"I couldn't find relevant information on the web for '{request.query}'.",
                (),
            )

        refs = search_service.to_source_references(results, request.request_id)

        context_parts = []
        for res in results:
            context_parts.append(
                f"TITLE: {res.title}\nURL: {res.url}\nCONTENT:\n{res.content}"
            )
        web_context = "\n\n---\n\n".join(context_parts)

        prompt = (
            "You are a web research assistant.\n\n"
            "Answer the user's question using ONLY the relevant information from the search results below.\n\n"
            "IMPORTANT:\n"
            "- Focus only on information relevant to the question.\n"
            "- Ignore unrelated content.\n"
            "- Do not reproduce entire webpages.\n"
            "- Give a concise, well-structured answer.\n"
            "- If sources disagree, mention the disagreement.\n"
            "- Include source URLs at the bottom if relevant.\n"
            "- Do not invent information.\n\n"
            f"SEARCH RESULTS:\n{web_context}\n\n"
            f"QUESTION:\n{request.query}"
        )

        if self._llm is not None and hasattr(self._llm, "generate"):
            try:
                answer = self._llm.generate(prompt, system="You are a concise enterprise web research assistant.")
                return AgentResponse(self.capability, answer.strip(), refs)
            except Exception as exc:
                logger.warning("LLM synthesis for web search failed: %s", exc)

        try:
            from backend.llm.groq_service import client, MODEL

            response = client.chat.completions.create(
                model=MODEL,
                messages=[
                    {"role": "system", "content": "You are a concise web research assistant."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.1,
            )
            answer = response.choices[0].message.content.strip()
            return AgentResponse(self.capability, answer, refs)
        except Exception as exc:
            logger.warning("Groq client synthesis failed, returning raw context: %s", exc)
            return AgentResponse(self.capability, f"### Web Search Results\n\n{web_context}", refs)


def run_web_agent(user_question: str) -> str:
    """Standalone web research helper function."""
    if not os.getenv("TAVILY_API_KEY"):
        return "Web search is unavailable: TAVILY_API_KEY is not configured."

    try:
        from backend.integrations.web import search_web
        from backend.llm.groq_service import client, MODEL

        results = search_web(user_question)
        if not results:
            return "I couldn't find relevant information on the web."

        context_parts = []
        for result in results:
            context_parts.append(
                f"TITLE: {result.get('title', '')}\nURL: {result.get('url', '')}\nCONTENT:\n{result.get('content', '')}"
            )
        context = "\n\n---\n\n".join(context_parts)

        prompt = f"""You are a web research assistant.

Answer the user's question using ONLY the relevant information
from the search results below.

IMPORTANT:
- Focus only on information relevant to the question.
- Ignore unrelated content.
- Do not reproduce entire webpages.
- Give a concise answer.
- If sources disagree, mention the disagreement.
- Include the source URLs.
- Do not invent information.

SEARCH RESULTS:
{context}

QUESTION:
{user_question}
"""
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": "You are a concise web research assistant."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
        )
        return response.choices[0].message.content.strip()
    except Exception as exc:
        return f"Error running web agent: {exc}"
