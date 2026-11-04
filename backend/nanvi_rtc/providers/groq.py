"""Groq adapter (OpenAI-compatible API). Provider-specific code lives only here.

Model names change over time: set GROQ_LLM_MODEL / GROQ_STT_MODEL / GROQ_TTS_MODEL.
"""
from __future__ import annotations

import io
import json
import os
import wave
from typing import AsyncIterator, Optional

import httpx

from .base import Capabilities, LLMProvider, STTProvider, TTSProvider

BASE = "https://api.groq.com/openai/v1"


def _client(api_key, client, timeout):
    if client is not None:
        return client
    key = api_key or os.environ.get("GROQ_API_KEY")
    if not key:
        raise RuntimeError("GROQ_API_KEY is not set")
    return httpx.AsyncClient(base_url=BASE, headers={"Authorization": f"Bearer {key}"}, timeout=timeout)


class GroqLLM(LLMProvider):
    name = "groq"
    capabilities = Capabilities(max_context_tokens=128_000, tool_calling=True,
                                languages=("en", "multi"),
                                limitations=("no native audio",))

    def __init__(self, api_key=None, model=None, client: Optional[httpx.AsyncClient] = None, **_):
        self.model = model or os.environ.get("GROQ_LLM_MODEL", "llama-3.3-70b-versatile")
        self._c = _client(api_key, client, 60)

    async def stream(self, messages, *, system=None) -> AsyncIterator[str]:
        msgs = ([{"role": "system", "content": system}] if system else []) + messages
        body = {"model": self.model, "messages": msgs, "stream": True}
        async with self._c.stream("POST", "/chat/completions", json=body) as r:
            if r.status_code >= 400:
                raise RuntimeError(f"groq llm http {r.status_code}: {(await r.aread())[:200]!r}")
            async for line in r.aiter_lines():
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    return
                delta = json.loads(data)["choices"][0].get("delta", {}).get("content")
                if delta:
                    yield delta

    async def aclose(self):
        await self._c.aclose()


class GroqSTT(STTProvider):
    name = "groq"
    capabilities = Capabilities(input_modalities=frozenset({"audio"}), streaming=False,
                                sample_rates=(16000,), languages=("multi",),
                                limitations=("request/response, not streaming",))

    def __init__(self, api_key=None, model=None, client=None, **_):
        self.model = model or os.environ.get("GROQ_STT_MODEL", "whisper-large-v3-turbo")
        self._c = _client(api_key, client, 30)

    async def transcribe(self, pcm_s16le, sample_rate=16000, language=None) -> str:
        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(sample_rate)
            w.writeframes(pcm_s16le)
        data = {"model": self.model, **({"language": language} if language else {})}
        r = await self._c.post("/audio/transcriptions", data=data,
                               files={"file": ("audio.wav", buf.getvalue(), "audio/wav")})
        r.raise_for_status()
        return r.json().get("text", "")


class GroqTTS(TTSProvider):
    name = "groq"
    capabilities = Capabilities(output_modalities=frozenset({"audio"}), streaming=False,
                                sample_rates=(24000,), word_alignment=False,
                                limitations=("no word alignment: continuation is chunk-level",))

    def __init__(self, api_key=None, model=None, voice=None, client=None, **_):
        # No default model: availability changes. Set GROQ_TTS_MODEL (UNVERIFIED against live API).
        self.model = model or os.environ.get("GROQ_TTS_MODEL")
        self.voice = voice or os.environ.get("GROQ_TTS_VOICE")
        if not self.model:
            raise RuntimeError("set GROQ_TTS_MODEL (and GROQ_TTS_VOICE if required)")
        self._c = _client(api_key, client, 30)

    async def synthesize(self, text: str) -> AsyncIterator[bytes]:
        body = {"model": self.model, "input": text, "response_format": "wav",
                **({"voice": self.voice} if self.voice else {})}
        r = await self._c.post("/audio/speech", json=body)
        r.raise_for_status()
        yield r.content
