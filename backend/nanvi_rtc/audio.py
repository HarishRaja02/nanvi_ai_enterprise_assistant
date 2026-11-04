"""Audio plumbing: energy VAD, turn/barge-in detection, and the PCM -> STT -> session pipeline.
Input format everywhere: 16 kHz, mono, PCM S16LE, 20 ms frames (640 bytes)."""
from __future__ import annotations

import array
import math
from dataclasses import dataclass, field
from typing import Optional

from .providers.base import STTProvider, VADProvider
from .session import AgentSession
from .types import ResponseStatus

FRAME_MS = 20
FRAME_BYTES = 16000 * 2 * FRAME_MS // 1000  # 640


def rms(pcm: bytes) -> float:
    a = array.array("h")
    a.frombytes(pcm[: len(pcm) // 2 * 2])
    return math.sqrt(sum(x * x for x in a) / len(a)) if a else 0.0


class EnergyVAD(VADProvider):
    """Adaptive-threshold energy VAD. Replaceable (e.g. Silero/WebRTC VAD) via the VADProvider interface."""
    name = "energy"

    def __init__(self, min_rms: float = 650.0, ratio: float = 3.2):
        self.min_rms, self.ratio, self.noise = min_rms, ratio, 100.0

    def is_speech(self, pcm_s16le_20ms: bytes) -> bool:
        level = rms(pcm_s16le_20ms)
        speech = level > max(self.min_rms, self.noise * self.ratio)
        if not speech:  # track the noise floor only on non-speech frames
            self.noise = 0.95 * self.noise + 0.05 * level
        return speech


@dataclass
class TurnDetector:
    """Frame-level state machine -> events: speech_start, barge_in, speech_end.

    barge_in fires only when the agent is speaking AND the user has produced `barge_in_ms` of
    continuous speech, so coughs and short backchannels ("mm-hmm") do not interrupt.
    """
    start_ms: int = 140
    end_ms: int = 500
    barge_in_ms: int = 350
    in_speech: bool = False
    _run: int = 0
    _sil: int = 0
    _barged: bool = False

    def feed(self, speech: bool, agent_speaking: bool) -> list[str]:
        ev: list[str] = []
        if speech:
            self._run += FRAME_MS
            self._sil = 0
            if not self.in_speech and self._run >= self.start_ms:
                self.in_speech, self._barged = True, False
                ev.append("speech_start")
            if self.in_speech and agent_speaking and not self._barged and self._run >= self.barge_in_ms:
                self._barged = True
                ev.append("barge_in")
        else:
            self._run = 0
            if self.in_speech:
                self._sil += FRAME_MS
                if self._sil >= self.end_ms:
                    self.in_speech = False
                    ev.append("speech_end")
        return ev


@dataclass
class AudioPipeline:
    """Feed 20 ms frames; finished utterances are transcribed and sent to the session."""
    session: AgentSession
    stt: STTProvider
    vad: VADProvider = field(default_factory=EnergyVAD)
    turn: TurnDetector = field(default_factory=TurnDetector)
    preroll_frames: int = 10
    max_utterance_s: float = 30.0
    allow_barge_in: bool = True  # multi-party policy hook: set per speaker
    _pre: list = field(default_factory=list)
    _utt: list = field(default_factory=list)

    def _agent_speaking(self) -> bool:
        cp = self.session.checkpoint
        return bool(cp and self.session._gen is not None)

    async def feed_frame(self, pcm: bytes) -> None:
        if len(pcm) != FRAME_BYTES:
            return  # drop malformed frames rather than corrupt the stream
        events = self.turn.feed(self.vad.is_speech(pcm), self._agent_speaking())
        if self.turn.in_speech or "speech_start" in events:
            if "speech_start" in events:
                self._utt = list(self._pre)
            self._utt.append(pcm)
            if len(self._utt) * FRAME_MS > self.max_utterance_s * 1000:
                events.append("speech_end")
        else:
            self._pre.append(pcm)
            del self._pre[: -self.preroll_frames]
        for e in events:
            if e == "barge_in" and self.allow_barge_in:
                await self.session.pause("barge_in")
            elif e == "speech_end":
                self.turn.in_speech = False
                if self._utt:
                    audio, self._utt = b"".join(self._utt), []
                    text = (await self.stt.transcribe(audio, 16000)).strip()
                    if text:
                        await self.session.handle_user_text(text)
                    else:
                        if self.session.checkpoint and self.session.checkpoint.status is ResponseStatus.PAUSED:
                            await self.session.resume_paused("silence_false_alarm")
                else:
                    if self.session.checkpoint and self.session.checkpoint.status is ResponseStatus.PAUSED:
                        await self.session.resume_paused("empty_speech_end")

