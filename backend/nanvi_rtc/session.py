"""AgentSession: generation, playback-confirmed delivery, interruption, pause and smart arbitration.

Invariants (each covered by tests/test_session.py):
  * Text counts as delivered only after the client acks its chunk.
  * Only one generation is current; chunks from stale generations are never emitted.
  * Pause halts playback without cancelling generation or discarding unspoken chunks.
  * False interrupts (backchannels, coughs, fillers, silence) automatically resume.
  * Valid interrupts cut off previous response and process the new user request.
  * "continue" resumes at the first unconfirmed chunk.
  * Provider failure never replays a response or retries automatically.
"""
from __future__ import annotations

import asyncio
import re
import time
from typing import Awaitable, Callable, Optional, Protocol

from .arbitrator import InterruptionArbitrator, InterruptionDecision
from .chunker import SentenceChunker
from .providers.base import LLMProvider, TTSProvider
from .providers.mock import CONTINUE_MARK
from .types import (ACTIVE, Chunk, Conversation, ResponseCheckpoint,
                    ResponseStatus, new_id)

_CONTINUE = re.compile(
    r"^\s*(ok(ay)?[, ]+)?(please\s+)?(continue|go on|keep going|carry on|go ahead|resume|proceed)\b[\s.!]*$",
    re.I)


def default_is_continue(text: str) -> bool:
    return bool(_CONTINUE.match(text))


class PlaybackSink(Protocol):
    async def send_chunk(self, *, response_id: str, generation_id: str, index: int,
                         text: str, audio: Optional[bytes]) -> None: ...
    async def stop(self, generation_id: str) -> None: ...
    async def emit(self, event: dict) -> None: ...


class AgentSession:
    def __init__(self, session_id: str, llm: LLMProvider, sink: PlaybackSink, *,
                 system_prompt: str = "You are a concise, friendly voice assistant. Speak in short sentences.",
                 tts: Optional[TTSProvider] = None, window: int = 2,
                 is_continue: Callable[[str], bool] = default_is_continue,
                 arbitrator: Optional[InterruptionArbitrator] = None,
                 clock: Optional[Callable[[], float]] = None):
        self.session_id, self.llm, self.sink, self.tts = session_id, llm, sink, tts
        self.window, self.is_continue = window, is_continue
        self.arbitrator = arbitrator or InterruptionArbitrator()
        self.conversation = Conversation(system_prompt)
        self._clock = clock or time.monotonic
        self._gen: Optional[str] = None
        self._task: Optional[asyncio.Task] = None
        self._cp: Optional[ResponseCheckpoint] = None
        self._paused: bool = False
        self._auto_resume_task: Optional[asyncio.Task] = None
        self._pump_lock: Optional[asyncio.Lock] = None
        self.metrics: list[dict] = []

    def _get_pump_lock(self) -> asyncio.Lock:
        if self._pump_lock is None:
            self._pump_lock = asyncio.Lock()
        return self._pump_lock

    # ---- public API -------------------------------------------------------
    def set_llm(self, llm: LLMProvider) -> None:
        """Swap provider. Context lives in Conversation, so nothing is lost; applies next generation."""
        self.llm = llm

    def close(self) -> None:
        """Cancel background tasks and clean up session resources."""
        if self._auto_resume_task and not self._auto_resume_task.done():
            self._auto_resume_task.cancel()
            self._auto_resume_task = None
        if self._task and not self._task.done():
            self._task.cancel()
            self._task = None

    @property
    def checkpoint(self) -> Optional[ResponseCheckpoint]:
        return self._cp

    @property
    def is_paused(self) -> bool:
        return self._paused

    async def _auto_resume_timer(self, gen: str, timeout_s: float = 2.5) -> None:
        try:
            await asyncio.sleep(timeout_s)
            if self._cp and self._cp.status is ResponseStatus.PAUSED and self._gen == gen:
                await self.resume_paused("auto_resume_timeout")
        except asyncio.CancelledError:
            pass

    async def pause(self, reason: str = "user_speech") -> bool:
        """Pause playback temporarily when user speech or barge-in is detected.
        Does NOT cancel generation or discard chunks. Auto-resumes after timeout if no input.
        """
        cp, gen = self._cp, self._gen
        if cp is None or gen is None or cp.status not in ACTIVE:
            return False
        self._paused = True
        cp.status = ResponseStatus.PAUSED
        if self._auto_resume_task and not self._auto_resume_task.done():
            self._auto_resume_task.cancel()
        self._auto_resume_task = asyncio.create_task(self._auto_resume_timer(gen, 2.5))
        await self.sink.stop(gen)
        await self.sink.emit({"type": "paused", "reason": reason, "checkpoint": cp.summary()})
        return True

    async def resume_paused(self, reason: str = "false_interrupt") -> bool:
        """Resume playback of the paused response from where it was paused."""
        if self._auto_resume_task and not self._auto_resume_task.done():
            self._auto_resume_task.cancel()
            self._auto_resume_task = None
        cp, gen = self._cp, self._gen
        if cp is None or gen is None or cp.status not in (ResponseStatus.PAUSED, ResponseStatus.SPEAKING):
            return False
        self._paused = False
        cp.status = ResponseStatus.SPEAKING if cp.llm_complete else ResponseStatus.GENERATING
        for c in cp.chunks:
            if not c.confirmed:
                c.sent = False  # re-send unconfirmed chunks
        await self.sink.emit({"type": "resumed", "reason": reason, "from_index": cp.confirmed_count, "checkpoint": cp.summary()})
        await self._pump(gen)
        await self._maybe_complete(cp, gen)
        return True

    async def handle_user_text(self, text: str) -> None:
        t0 = self._clock()
        cp = self._cp
        agent_text = cp.generated_text if cp else None
        decision = self.arbitrator.classify(text, agent_text=agent_text)

        # Active turn (SPEAKING, GENERATING, or PAUSED)
        if cp and cp.status in ACTIVE:
            if decision is InterruptionDecision.RESUME:
                # False interrupt (backchannel/silence/speaker echo/continue) -> Resume!
                self.metrics.append({"type": "false_interrupt_resumed", "input": text})
                if cp.status is ResponseStatus.PAUSED:
                    await self.resume_paused("false_interrupt")
                return

            if decision is InterruptionDecision.HOLD:
                # User asked to wait/hold -> stay paused without auto-resuming
                if self._auto_resume_task and not self._auto_resume_task.done():
                    self._auto_resume_task.cancel()
                    self._auto_resume_task = None
                if cp.status is not ResponseStatus.PAUSED:
                    await self.pause("user_hold")
                    if self._auto_resume_task and not self._auto_resume_task.done():
                        self._auto_resume_task.cancel()
                        self._auto_resume_task = None
                await self.sink.emit({"type": "holding", "input": text, "checkpoint": cp.summary()})
                return

            # Valid user interrupt -> cut off previous response
            await self.interrupt("valid_user_interrupt")
            if not cp.committed:
                cp.status = ResponseStatus.DISCARDED
                self._finalize(cp)

            cleaned = re.sub(r"[^\w\s]", "", text.strip().lower())
            if cleaned in {"stop", "cancel", "shut up", "be quiet", "silence"}:
                await self.sink.emit({"type": "stopped", "reason": "user_command", "checkpoint": cp.summary()})
                return

        # Interrupted turn
        elif cp and cp.status is ResponseStatus.INTERRUPTED and not cp.committed:
            if decision is InterruptionDecision.RESUME or self.is_continue(text):
                await self._resume(cp, t0)
                return
            else:
                cp.status = ResponseStatus.DISCARDED
                self._finalize(cp)
                cleaned = re.sub(r"[^\w\s]", "", text.strip().lower())
                if cleaned in {"stop", "cancel", "shut up", "be quiet", "silence"}:
                    return

        text = text.strip()
        if not text:
            return

        self.conversation.add_user(text)
        await self._start(self.conversation.messages(), t0)

    async def interrupt(self, reason: str = "user") -> bool:
        cp, gen = self._cp, self._gen
        if cp is None or gen is None or cp.status not in ACTIVE:
            return False
        t0 = self._clock()
        self._paused = False
        if self._auto_resume_task and not self._auto_resume_task.done():
            self._auto_resume_task.cancel()
            self._auto_resume_task = None
        self._gen = None  # from here on, nothing for `gen` may be emitted
        task, self._task = self._task, None
        if task and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        cp.status = ResponseStatus.INTERRUPTED
        await self.sink.stop(gen)
        self.metrics.append({"type": "interrupt_to_stop_ms", "value": (self._clock() - t0) * 1000})
        await self.sink.emit({"type": "interrupted", "reason": reason, "checkpoint": cp.summary()})
        return True

    async def on_chunk_ack(self, response_id: str, generation_id: str, index: int) -> None:
        cp = self._cp
        if cp is None or generation_id != self._gen or cp.response_id != response_id \
                or not (0 <= index < len(cp.chunks)):
            self.metrics.append({"type": "stale_ack", "value": 1})
            return
        cp.chunks[index].confirmed = True
        await self._pump(generation_id)
        await self._maybe_complete(cp, generation_id)

    async def wait_generation(self) -> None:
        """Wait until the current LLM generation task has finished (not playback)."""
        if self._task:
            await asyncio.gather(self._task, return_exceptions=True)

    # ---- internals --------------------------------------------------------
    async def _start(self, messages: Optional[list[dict]], t0: float) -> None:
        self._paused = False
        gen = new_id()
        cp = ResponseCheckpoint(self.session_id, new_id(), gen, turn_started_at=t0)
        self._cp, self._gen = cp, gen
        self._task = asyncio.create_task(self._run(gen, cp, messages))

    async def _resume(self, cp: ResponseCheckpoint, t0: float) -> None:
        self._paused = False
        gen = new_id()
        cp.generation_id, cp.turn_started_at, cp.first_sent_at = gen, t0, None
        for c in cp.chunks:
            if not c.confirmed:
                c.sent = False  # re-send everything not confirmed heard
        messages = None
        if cp.llm_complete:
            cp.status = ResponseStatus.SPEAKING
        else:
            cp.status = ResponseStatus.GENERATING
            messages = self.conversation.messages() + [
                {"role": "assistant", "content": cp.generated_text},
                {"role": "user", "content": f"{CONTINUE_MARK} Continue exactly where you stopped. Do not repeat anything."},
            ]
        self._gen = gen
        await self.sink.emit({"type": "resumed", "from_index": cp.confirmed_count, "checkpoint": cp.summary()})
        self._task = asyncio.create_task(self._run(gen, cp, messages))

    async def _run(self, gen: str, cp: ResponseCheckpoint, messages: Optional[list[dict]]) -> None:
        try:
            await self._pump(gen)
            if messages is not None:
                chunker = SentenceChunker()
                async for tok in self.llm.stream(messages, system=self.conversation.system_prompt):
                    if gen != self._gen:
                        return
                    for text in chunker.feed(tok):
                        cp.chunks.append(Chunk(len(cp.chunks), text))
                        await self._pump(gen)
                for text in chunker.flush():
                    cp.chunks.append(Chunk(len(cp.chunks), text))
                    await self._pump(gen)
            cp.llm_complete = True
            if gen == self._gen:
                if cp.status is not ResponseStatus.PAUSED:
                    cp.status = ResponseStatus.SPEAKING
                await self._maybe_complete(cp, gen)
        except asyncio.CancelledError:
            raise
        except Exception as e:  # provider failure: no replay, no automatic retry
            if gen == self._gen:
                cp.error, cp.llm_complete = str(e), True
                cp.status = ResponseStatus.SPEAKING
                await self.sink.emit({"type": "error", "where": "llm", "message": str(e)})
                await self._maybe_complete(cp, gen)

    async def _pump(self, gen: str) -> None:
        async with self._get_pump_lock():
            cp = self._cp
            while cp is not None and gen == self._gen and not self._paused:
                inflight = sum(1 for c in cp.chunks if c.sent and not c.confirmed)
                nxt = next((c for c in cp.chunks if not c.sent and not c.confirmed), None)
                if nxt is None or inflight >= self.window:
                    return
                audio = None
                if self.tts is not None:
                    audio = b"".join([p async for p in self.tts.synthesize(nxt.text)])
                if gen != self._gen or self._paused:  # re-check after await: never emit while paused or stale
                    return
                nxt.sent = True
                if cp.first_sent_at is None:
                    cp.first_sent_at = self._clock()
                    self.metrics.append({"type": "first_chunk_ms",
                                         "value": (cp.first_sent_at - cp.turn_started_at) * 1000})
                await self.sink.send_chunk(response_id=cp.response_id, generation_id=gen,
                                           index=nxt.index, text=nxt.text, audio=audio)

    async def _maybe_complete(self, cp: ResponseCheckpoint, gen: str) -> None:
        if gen != self._gen or not cp.llm_complete or cp.status is not ResponseStatus.SPEAKING or self._paused:
            return
        if any(not c.confirmed for c in cp.chunks):
            return
        cp.status = ResponseStatus.FAILED if cp.error else ResponseStatus.COMPLETED
        self._gen = None
        self._finalize(cp)
        await self.sink.emit({"type": "response_done", "checkpoint": cp.summary()})

    def _finalize(self, cp: ResponseCheckpoint) -> None:
        if cp.committed:
            return
        cp.committed = True
        self.conversation.add_assistant(cp.confirmed_text,
                                        interrupted=cp.status is not ResponseStatus.COMPLETED)
