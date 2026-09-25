from __future__ import annotations

import threading
import time
from abc import ABC, abstractmethod


class RateLimitExceeded(Exception):
    """Raised when a caller exceeds a configured rate limit."""


class RateLimiter(ABC):
    @abstractmethod
    def check(self, key: str) -> None:
        raise NotImplementedError


class NoOpRateLimiter(RateLimiter):
    """Development/testing only; never a production protection."""
    def check(self, key: str) -> None:
        return None


class InMemoryFixedWindowRateLimiter(RateLimiter):
    """Single-process limiter for local development and deterministic tests."""
    def __init__(self, max_requests: int = 60, window_seconds: int = 60) -> None:
        if max_requests <= 0 or window_seconds <= 0:
            raise ValueError("rate-limit settings must be positive")
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._lock = threading.Lock()
        self._windows: dict[str, tuple[int, float]] = {}

    def check(self, key: str) -> None:
        now = time.monotonic()
        with self._lock:
            count, start = self._windows.get(key, (0, now))
            if now - start >= self.window_seconds:
                count, start = 0, now
            if count >= self.max_requests:
                raise RateLimitExceeded(key)
            self._windows[key] = (count + 1, start)
