"""Core data model: response checkpoints and conversation state (provider-independent)."""
from __future__ import annotations

import enum
import uuid
from dataclasses import dataclass, field
from typing import Optional


class ResponseStatus(str, enum.Enum):
    GENERATING = "generating"
    SPEAKING = "speaking"
    PAUSED = "paused"
    COMPLETED = "completed"
    INTERRUPTED = "interrupted"
    DISCARDED = "discarded"
    FAILED = "failed"


ACTIVE = (ResponseStatus.GENERATING, ResponseStatus.SPEAKING, ResponseStatus.PAUSED)


@dataclass
class Chunk:
    index: int
    text: str
    sent: bool = False       # handed to the playback sink
    confirmed: bool = False  # client acknowledged it finished playing


@dataclass
class ResponseCheckpoint:
    session_id: str
    response_id: str
    generation_id: str
    chunks: list[Chunk] = field(default_factory=list)
    status: ResponseStatus = ResponseStatus.GENERATING
    llm_complete: bool = False
    error: Optional[str] = None
    committed: bool = False
    turn_started_at: float = 0.0
    first_sent_at: Optional[float] = None

    @property
    def generated_text(self) -> str:
        return " ".join(c.text for c in self.chunks)

    @property
    def confirmed_count(self) -> int:
        """Length of the contiguous confirmed prefix: the confirmed playback position."""
        n = 0
        for c in self.chunks:
            if not c.confirmed:
                break
            n += 1
        return n

    @property
    def confirmed_text(self) -> str:
        return " ".join(c.text for c in self.chunks[: self.confirmed_count])

    @property
    def unspoken_text(self) -> str:
        return " ".join(c.text for c in self.chunks[self.confirmed_count :])

    def summary(self) -> dict:
        return {
            "session_id": self.session_id,
            "response_id": self.response_id,
            "generation_id": self.generation_id,
            "status": self.status.value,
            "chunk_count": len(self.chunks),
            "confirmed_index": self.confirmed_count - 1,
            "confirmed_text": self.confirmed_text,
            "unspoken_text": self.unspoken_text,
        }


def new_id() -> str:
    return uuid.uuid4().hex[:12]


@dataclass
class Turn:
    role: str  # "user" | "assistant"
    text: str
    interrupted: bool = False


class Conversation:
    """Provider-independent context. Holds only text that was actually delivered."""

    def __init__(self, system_prompt: str):
        self.system_prompt = system_prompt
        self.turns: list[Turn] = []

    def add_user(self, text: str) -> None:
        self.turns.append(Turn("user", text))

    def add_assistant(self, text: str, interrupted: bool = False) -> None:
        if text.strip():
            self.turns.append(Turn("assistant", text, interrupted))

    def messages(self) -> list[dict]:
        out = []
        for t in self.turns:
            content = t.text + (" [interrupted by the user]" if t.interrupted else "")
            out.append({"role": t.role, "content": content})
        return out

