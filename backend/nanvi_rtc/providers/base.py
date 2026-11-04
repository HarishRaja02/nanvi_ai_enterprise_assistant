"""Provider interfaces + declared capabilities. No provider SDK may be imported here."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import AsyncIterator, Optional


@dataclass(frozen=True)
class Capabilities:
    input_modalities: frozenset = frozenset({"text"})
    output_modalities: frozenset = frozenset({"text"})
    streaming: bool = True
    cancellation: bool = True
    native_audio: bool = False
    max_context_tokens: int = 8192
    sample_rates: tuple = ()
    languages: tuple = ("en",)
    tool_calling: bool = False
    session_resumption: bool = False
    word_alignment: bool = False  # TTS returns text<->audio timestamps (enables exact continuation)
    limitations: tuple = ()


class _Provider(ABC):
    name: str = "unnamed"
    capabilities: Capabilities = Capabilities()

    async def aclose(self) -> None:  # optional cleanup
        return None


class LLMProvider(_Provider):
    @abstractmethod
    def stream(self, messages: list[dict], *, system: Optional[str] = None) -> AsyncIterator[str]:
        """Yield text deltas. Must stop promptly when the consuming task is cancelled."""


class STTProvider(_Provider):
    @abstractmethod
    async def transcribe(self, pcm_s16le: bytes, sample_rate: int = 16000,
                         language: Optional[str] = None) -> str: ...


class TTSProvider(_Provider):
    @abstractmethod
    def synthesize(self, text: str) -> AsyncIterator[bytes]:
        """Yield audio bytes for one chunk of text."""


class VADProvider(_Provider):
    @abstractmethod
    def is_speech(self, pcm_s16le_20ms: bytes) -> bool: ...


class RealtimeAudioProvider(_Provider):
    """Native audio-in/audio-out sessions. Interface only in v0.3 (see docs/agent_runtime.md)."""

    @abstractmethod
    async def connect(self, *, system: str, history: list[dict]) -> None: ...

    @abstractmethod
    async def send_audio(self, pcm_s16le: bytes) -> None: ...

    @abstractmethod
    def events(self) -> AsyncIterator[dict]: ...

    @abstractmethod
    async def cancel_response(self) -> None: ...
