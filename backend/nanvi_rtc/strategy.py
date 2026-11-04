"""Pick an execution pipeline from declared provider capabilities."""
from __future__ import annotations

from .providers.base import RealtimeAudioProvider


def select_strategy(*, stt=None, llm=None, tts=None, realtime=None) -> str:
    if realtime is not None and isinstance(realtime, RealtimeAudioProvider) \
            and realtime.capabilities.native_audio:
        return "realtime"
    if llm is not None and llm.capabilities.streaming:
        return "cascaded" if (stt is not None and tts is not None) else "text-cascaded"
    raise ValueError("no usable provider combination: need a streaming LLM or a realtime audio provider")
