"""Google Gemini adapter (REST + SSE). Provider-specific code lives only here.

Set GEMINI_LLM_MODEL to change the model. Native realtime audio (Live API) is declared
but not implemented in v0.3.
"""
from __future__ import annotations

import json
import os
from typing import AsyncIterator, Optional

import httpx

from .base import Capabilities, LLMProvider

BASE = "https://generativelanguage.googleapis.com/v1beta"


class GeminiLLM(LLMProvider):
    name = "gemini"
    capabilities = Capabilities(input_modalities=frozenset({"text", "image", "audio"}),
                                max_context_tokens=1_000_000, tool_calling=True,
                                languages=("multi",),
                                limitations=("text streaming only in this adapter",))

    def __init__(self, api_key=None, model=None, client: Optional[httpx.AsyncClient] = None, **_):
        self.model = model or os.environ.get("GEMINI_LLM_MODEL", "gemini-2.0-flash")
        key = api_key or os.environ.get("GEMINI_API_KEY")
        if client is None and not key:
            raise RuntimeError("GEMINI_API_KEY is not set")
        self._c = client or httpx.AsyncClient(base_url=BASE, headers={"x-goog-api-key": key}, timeout=60)

    async def stream(self, messages, *, system=None) -> AsyncIterator[str]:
        contents = [{"role": "model" if m["role"] == "assistant" else "user",
                     "parts": [{"text": m["content"]}]} for m in messages]
        body: dict = {"contents": contents}
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}
        url = f"/models/{self.model}:streamGenerateContent?alt=sse"
        async with self._c.stream("POST", url, json=body) as r:
            if r.status_code >= 400:
                raise RuntimeError(f"gemini http {r.status_code}: {(await r.aread())[:200]!r}")
            async for line in r.aiter_lines():
                if not line.startswith("data:"):
                    continue
                for cand in json.loads(line[5:]).get("candidates", []):
                    for part in cand.get("content", {}).get("parts", []):
                        if part.get("text"):
                            yield part["text"]

    async def aclose(self):
        await self._c.aclose()
