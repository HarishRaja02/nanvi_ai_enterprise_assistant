from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4

from backend.core.resilience import RetryPolicy, retry_idempotent
from backend.observability.logging import get_correlation_id, get_request_id, log_event

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Job:
    job_id: str
    name: str
    payload: dict
    created_at: datetime
    request_id: str | None = None
    correlation_id: str | None = None


class JobQueue(ABC):
    @abstractmethod
    def enqueue(self, name: str, payload: dict) -> Job:
        raise NotImplementedError


class InMemoryJobQueue(JobQueue):
    """Prototype queue only; jobs are lost on process restart."""
    def __init__(self) -> None:
        self.jobs: list[Job] = []

    def enqueue(self, name: str, payload: dict) -> Job:
        job = Job(uuid4().hex, name, payload, datetime.now(timezone.utc), get_request_id() if get_request_id() != "-" else None, get_correlation_id() if get_correlation_id() != "-" else None)
        self.jobs.append(job)
        return job


class RedisJobQueue(JobQueue):
    """Durable queue with atomic enqueue idempotency and bounded retries."""
    _ENQUEUE_SCRIPT = """
    if redis.call('SETNX', KEYS[1], ARGV[1]) == 1 then
      redis.call('EXPIRE', KEYS[1], ARGV[2])
      redis.call('RPUSH', KEYS[2], ARGV[3])
      return 1
    end
    return 0
    """

    def __init__(self, redis_url: str, queue_name: str = "nanvi:jobs", retry_policy: RetryPolicy | None = None) -> None:
        try:
            import redis
        except ImportError as exc:
            raise RuntimeError("Redis jobs require the redis package") from exc
        self._client = redis.Redis.from_url(redis_url, decode_responses=True)
        self._queue_name = queue_name
        self._retry_policy = retry_policy or RetryPolicy(attempts=2)

    def enqueue(self, name: str, payload: dict) -> Job:
        job = Job(uuid4().hex, name, payload, datetime.now(timezone.utc), get_request_id() if get_request_id() != "-" else None, get_correlation_id() if get_correlation_id() != "-" else None)
        encoded = json.dumps({"job_id": job.job_id, "name": name, "payload": payload, "created_at": job.created_at.isoformat(), "request_id": job.request_id, "correlation_id": job.correlation_id}, separators=(",", ":"))
        marker = f"{self._queue_name}:idempotency:{job.job_id}"

        def operation():
            return self._client.eval(self._ENQUEUE_SCRIPT, 2, marker, self._queue_name, job.job_id, "86400", encoded)

        try:
            retry_idempotent(operation, policy=self._retry_policy,
                             retry_if=lambda exc: self._is_transient_redis(exc))
        except Exception as exc:
            log_event(logger, "redis_enqueue_failed", logging.ERROR, queue=self._queue_name, exception_type=type(exc).__name__)
            raise RuntimeError("Job queue is temporarily unavailable") from exc
        log_event(logger, "redis_enqueue_completed", job_id=job.job_id, queue=self._queue_name, job_name=name)
        return job

    @staticmethod
    def _is_transient_redis(exc: Exception) -> bool:
        name = type(exc).__name__.casefold()
        return any(x in name for x in ("connection", "timeout", "busy", "temporarily"))
