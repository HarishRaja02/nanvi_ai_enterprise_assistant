"""Enterprise Web Search integration powered by Tavily."""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
import uuid

from backend.sources.models import SourceReference, SourceType
from backend.observability.logging import log_event

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class WebSearchResult:
    title: str
    url: str
    content: str
    score: float = 0.0


class WebSearchService:
    """Enterprise web search service leveraging Tavily API."""

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = (api_key or os.getenv("TAVILY_API_KEY", "")).strip()
        self._client = None
        if self._api_key:
            try:
                from tavily import TavilyClient
                self._client = TavilyClient(api_key=self._api_key)
            except Exception as exc:
                logger.warning("Failed to initialize TavilyClient: %s", exc)

    @property
    def is_configured(self) -> bool:
        return self._client is not None

    def search(self, query: str, max_results: int = 5) -> list[WebSearchResult]:
        """Execute a web search query with bounded content length and error resilience."""
        if not self._client:
            log_event(logger, "web_search_skipped_not_configured", logging.INFO)
            return []

        clean_query = query.strip()
        if not clean_query:
            return []

        try:
            log_event(logger, "web_search_request_started", query_length=len(clean_query))
            response = self._client.search(
                query=clean_query,
                search_depth="advanced",
                max_results=max_results,
            )
            raw_items = response.get("results", [])
            results: list[WebSearchResult] = []
            for item in raw_items:
                raw_text = item.get("content", "")
                trimmed = raw_text[:1800] if raw_text else ""
                results.append(
                    WebSearchResult(
                        title=item.get("title") or "Web Information",
                        url=item.get("url") or "",
                        content=trimmed,
                        score=float(item.get("score") or 0.0),
                    )
                )

            log_event(logger, "web_search_request_completed", result_count=len(results))
            return results
        except Exception as exc:
            log_event(logger, "web_search_request_failed", logging.ERROR, exception_type=type(exc).__name__)
            return []

    def to_source_references(self, results: list[WebSearchResult], request_id: str | None = None) -> tuple[SourceReference, ...]:
        """Convert web search results into immutable SourceReference provenance objects."""
        refs: list[SourceReference] = []
        now = datetime.now(timezone.utc)
        for r in results:
            if not r.url:
                continue
            ref_id = f"web-{uuid.uuid4().hex[:12]}"
            refs.append(
                SourceReference(
                    reference_id=ref_id,
                    source_type=SourceType.WEBSITE,
                    display_name=r.title,
                    title=r.title,
                    location=r.url,
                    href=r.url,
                    timestamp=now,
                    mime_type="text/html",
                )
            )
        return tuple(refs)
