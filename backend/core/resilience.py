from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass
from typing import Callable, TypeVar

T = TypeVar("T")
logger = logging.getLogger(__name__)


class DependencyFailure(RuntimeError):
    """Safe application-level dependency failure; never contains secrets."""


class DependencyTimeout(DependencyFailure):
    pass


class DependencyUnavailable(DependencyFailure):
    pass


class InvalidDependencyResponse(DependencyFailure):
    pass


@dataclass(frozen=True)
class RetryPolicy:
    attempts: int = 2
    base_delay_seconds: float = 0.05
    max_delay_seconds: float = 0.5

    def __post_init__(self) -> None:
        if self.attempts < 1 or self.base_delay_seconds < 0 or self.max_delay_seconds < 0:
            raise ValueError("Invalid retry policy")


def retry_idempotent(operation: Callable[[], T], *, policy: RetryPolicy,
                     retry_if: Callable[[Exception], bool]) -> T:
    """Retry only operations explicitly known to be safe/idempotent."""
    last: Exception | None = None
    for attempt in range(policy.attempts):
        try:
            return operation()
        except Exception as exc:  # classify below; do not leak internals
            last = exc
            if attempt + 1 >= policy.attempts or not retry_if(exc):
                raise
            delay = min(policy.max_delay_seconds, policy.base_delay_seconds * (2 ** attempt))
            if delay:
                time.sleep(delay * random.uniform(0.8, 1.2))
    assert last is not None
    raise last
