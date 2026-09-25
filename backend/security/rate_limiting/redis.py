from __future__ import annotations

from .limiter import RateLimitExceeded, RateLimiter


class RedisFixedWindowRateLimiter(RateLimiter):
    """Distributed fixed-window limiter. Requires the redis Python package."""
    def __init__(self, redis_url: str, max_requests: int = 60, window_seconds: int = 60) -> None:
        if not redis_url:
            raise ValueError("REDIS_URL is required")
        if max_requests <= 0 or window_seconds <= 0:
            raise ValueError("rate-limit settings must be positive")
        try:
            import redis
        except ImportError as exc:
            raise RuntimeError("Redis rate limiting requires the redis package") from exc
        self._client = redis.Redis.from_url(redis_url, decode_responses=True)
        self._max = max_requests
        self._window = window_seconds

    def check(self, key: str) -> None:
        bucket = f"nanvi:rate:{key}"
        count = self._client.incr(bucket)
        if count == 1:
            self._client.expire(bucket, self._window)
        if count > self._max:
            raise RateLimitExceeded(key)
