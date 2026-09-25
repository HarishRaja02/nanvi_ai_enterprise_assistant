"""Groq service compatibility module providing an OpenAI-compatible client and default MODEL."""
from __future__ import annotations

import os
from types import SimpleNamespace
import httpx
from dotenv import load_dotenv

load_dotenv()

MODEL = os.getenv("LLM_MODEL", "llama-3.3-70b-versatile")
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"


class _ChatCompletions:
    def create(
        self,
        model: str | None = None,
        messages: list[dict[str, str]] | None = None,
        temperature: float = 0.1,
        max_tokens: int = 2048,
        **kwargs,
    ):
        api_key = os.getenv("GROQ_API_KEY", "")
        model_name = model or MODEL
        payload = {
            "model": model_name,
            "messages": messages or [],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        max_retries = 3
        retry_delay = 1.0

        for attempt in range(max_retries):
            try:
                resp = httpx.post(
                    GROQ_API_URL,
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                    timeout=30.0,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    choices = data.get("choices") or []
                    if choices and "message" in choices[0]:
                        content = choices[0]["message"].get("content", "")
                    else:
                        content = "No response choices returned by AI provider."
                    break
                elif resp.status_code in (429, 500, 502, 503, 504):
                    if attempt < max_retries - 1:
                        import time
                        time.sleep(retry_delay)
                        retry_delay *= 2
                        continue
                    else:
                        content = f"Error during AI generation: HTTP {resp.status_code} - {resp.text}"
                        break
                else:
                    content = f"Error during AI generation: HTTP {resp.status_code} - {resp.text}"
                    break
            except Exception as exc:
                if attempt < max_retries - 1:
                    import time
                    time.sleep(retry_delay)
                    retry_delay *= 2
                    continue
                else:
                    content = f"Error during AI generation: {exc}"
                    break

        msg_obj = SimpleNamespace(content=content)
        choice_obj = SimpleNamespace(message=msg_obj)
        return SimpleNamespace(choices=[choice_obj])


class _Chat:
    def __init__(self):
        self.completions = _ChatCompletions()


class GroqClient:
    def __init__(self):
        self.chat = _Chat()


client = GroqClient()
