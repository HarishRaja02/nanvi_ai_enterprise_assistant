"""Provider registry with lazy factories: adapters are imported only when requested."""
from __future__ import annotations

import importlib
from typing import Callable

KINDS = ("stt", "llm", "tts", "realtime", "vad")


class Registry:
    def __init__(self) -> None:
        self._f: dict[tuple[str, str], Callable] = {}

    def register(self, kind: str, name: str, factory: Callable) -> None:
        if kind not in KINDS:
            raise ValueError(f"unknown provider kind {kind!r}")
        self._f[(kind, name)] = factory

    def register_lazy(self, kind: str, name: str, module: str, cls: str) -> None:
        def factory(**kw):
            return getattr(importlib.import_module(module), cls)(**kw)
        self.register(kind, name, factory)

    def create(self, kind: str, name: str, **config):
        try:
            return self._f[(kind, name)](**config)
        except KeyError:
            raise KeyError(f"no {kind} provider named {name!r}; have {self.names(kind)}") from None

    def names(self, kind: str) -> list[str]:
        return sorted(n for k, n in self._f if k == kind)

    def capabilities(self, kind: str, name: str, **config):
        return self.create(kind, name, **config).capabilities


registry = Registry()
_pkg = __name__.rsplit(".", 1)[0]
registry.register_lazy("llm", "mock", f"{_pkg}.mock", "MockLLM")
registry.register_lazy("stt", "mock", f"{_pkg}.mock", "MockSTT")
registry.register_lazy("tts", "mock", f"{_pkg}.mock", "MockTTS")
registry.register_lazy("llm", "groq", f"{_pkg}.groq", "GroqLLM")
registry.register_lazy("stt", "groq", f"{_pkg}.groq", "GroqSTT")
registry.register_lazy("tts", "groq", f"{_pkg}.groq", "GroqTTS")
registry.register_lazy("llm", "gemini", f"{_pkg}.gemini", "GeminiLLM")
registry.register_lazy("llm", "nanvi", f"{_pkg}.nanvi_enterprise", "NanviEnterpriseLLM")
