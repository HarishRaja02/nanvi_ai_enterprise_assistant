import os
from dotenv import load_dotenv
from tavily import TavilyClient

load_dotenv()

_API_KEY = os.getenv("TAVILY_API_KEY", "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")
client = TavilyClient(api_key=_API_KEY) if _API_KEY else None


def search_web(query: str, max_results: int = 5) -> list[dict]:
    """Search the web using Tavily API and return structured results."""
    global client
    api_key = os.getenv("TAVILY_API_KEY", _API_KEY)
    if not client and api_key:
        client = TavilyClient(api_key=api_key)

    if not client:
        return []

    try:
        response = client.search(
            query=query,
            search_depth="advanced",
            max_results=max_results,
        )
    except Exception:
        return []

    results = []
    for item in response.get("results", []):
        raw_content = item.get("content", "")
        # Keep a useful portion of the search result for LLM synthesis
        trimmed_content = raw_content[:1800] if raw_content else ""
        results.append({
            "title": item.get("title", "Web Result"),
            "url": item.get("url", ""),
            "content": trimmed_content,
        })

    return results
