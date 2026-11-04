"""Splits a token stream into speakable chunks (sentences)."""
import re

_END = re.compile(r"(?<=[.!?])\s+|\n+")


class SentenceChunker:
    def __init__(self, min_chars: int = 12, max_chars: int = 220):
        self.min_chars, self.max_chars, self._buf = min_chars, max_chars, ""

    def feed(self, token: str) -> list[str]:
        self._buf += token
        out: list[str] = []
        while True:
            m = _END.search(self._buf)
            if m and m.start() + 1 >= self.min_chars:
                out.append(self._buf[: m.start() + (1 if self._buf[m.start()] in ".!?" else 0)].strip())
                self._buf = self._buf[m.end():]
                continue
            if len(self._buf) > self.max_chars:
                cut = max(self._buf.rfind(", ", 0, self.max_chars), self._buf.rfind(" ", 0, self.max_chars))
                cut = cut if cut > 0 else self.max_chars
                out.append(self._buf[:cut].strip())
                self._buf = self._buf[cut:].lstrip(", ")
                continue
            break
        return [c for c in out if c]

    def flush(self) -> list[str]:
        rest, self._buf = self._buf.strip(), ""
        return [rest] if rest else []
