from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable

from .queue import Job
from backend.observability.logging import log_event

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class WorkerResult:
    job_id: str
    succeeded: bool
    attempts: int
    error: str | None = None


class JobWorker:
    """Small failure-safe worker contract used by tests and future queue runners.

    A failed handler is never acknowledged as successful. Retries are reserved for
    handlers declared retryable by the caller; no arbitrary side effects are retried.
    """

    def __init__(self, max_attempts: int = 3) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts must be positive")
        self._max_attempts = max_attempts

    def process(self, job: Job, handler: Callable[[Job], None],
                *, retryable: Callable[[Exception], bool] | None = None) -> WorkerResult:
        attempts = 0
        while attempts < self._max_attempts:
            attempts += 1
            try:
                handler(job)
                log_event(logger, "worker_job_completed", job_id=job.job_id, job_name=job.name, attempt=attempts, request_id=job.request_id, correlation_id=job.correlation_id)
                return WorkerResult(job.job_id, True, attempts)
            except Exception as exc:
                retry = retryable(exc) if retryable else False
                log_event(logger, "worker_job_failed", logging.ERROR, job_id=job.job_id, job_name=job.name, attempt=attempts, retry=retry, exception_type=type(exc).__name__, request_id=job.request_id, correlation_id=job.correlation_id)
                if not retry or attempts >= self._max_attempts:
                    return WorkerResult(job.job_id, False, attempts, "Job processing failed")
        return WorkerResult(job.job_id, False, attempts, "Job processing failed")
