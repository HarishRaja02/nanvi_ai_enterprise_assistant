"""Offline providers: let the whole runtime (and the browser demo) work with no API keys."""
from __future__ import annotations

import asyncio
from typing import AsyncIterator, Optional

from .base import Capabilities, LLMProvider, STTProvider, TTSProvider

CONTINUE_MARK = "[continue]"

_BODY = [
    "Real-time voice systems work best when every stage streams its output.",
    "The media path should never wait for a language model to finish thinking.",
    "Interruptions must stop playback on the device first, and the server second.",
    "Only text the listener actually heard should count as part of the conversation.",
    "When you say continue, the assistant resumes from the last confirmed sentence.",
    "If you change the subject instead, the unspoken remainder is simply dropped.",
]


class MockLLM(LLMProvider):
    name = "mock"
    capabilities = Capabilities(limitations=("canned responses",))

    def __init__(self, token_delay: float = 0.02, **_):
        self.token_delay = token_delay

    async def stream(self, messages: list[dict], *, system: Optional[str] = None) -> AsyncIterator[str]:
        last = messages[-1]["content"] if messages else ""
        if last.startswith(CONTINUE_MARK):
            text = "Here is the rest of the explanation. " + " ".join(_BODY[3:]) + " That is everything."
        else:
            text = f"You asked: {last.strip()[:80]}. " + " ".join(_BODY)
        for word in text.split(" "):
            await asyncio.sleep(self.token_delay)
            yield word + " "


class MockSTT(STTProvider):
    name = "mock"
    capabilities = Capabilities(input_modalities=frozenset({"audio"}), sample_rates=(16000,))

    async def transcribe(self, pcm_s16le, sample_rate=16000, language=None) -> str:
        return "(mock transcript)"


class MockTTS(TTSProvider):
    name = "mock"
    capabilities = Capabilities(output_modalities=frozenset({"audio"}), sample_rates=(16000,))

    async def synthesize(self, text: str) -> AsyncIterator[bytes]:
        yield b"\x00\x00" * 160 * max(1, len(text) // 8)  # silence sized roughly to text
