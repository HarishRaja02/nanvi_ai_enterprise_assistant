"""Groq LLM provider using the OpenAI-compatible chat completions API.

The ``GROQ_API_KEY`` is read from server-side configuration and NEVER:
- placed in prompt context or graph state
- sent to the frontend
- logged
- included in API responses
"""
from __future__ import annotations

import logging
import random
import time
from threading import BoundedSemaphore, Lock
from typing import Sequence

import httpx

from backend.core.config import settings
from backend.llm.provider import BaseLLMProvider, LLMNotConfiguredError, LLMProviderError
from backend.observability.logging import log_event

logger = logging.getLogger(__name__)

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"


class GroqProvider(BaseLLMProvider):
    """Groq cloud provider with concurrency limiting, circuit breaking, and jittered backoff."""

    _concurrency_limiter: BoundedSemaphore | None = None
    _circuit_lock = Lock()
    _circuit_open_until: float = 0.0
    _consecutive_rate_limits: int = 0

    def __init__(self, api_key: str, model: str, timeout: float = 30.0) -> None:
        super().__init__(model)
        if not api_key:
            raise LLMNotConfiguredError(
                "AI service is not configured. Set GROQ_API_KEY in the backend environment."
            )
        self._api_key = api_key
        self._timeout = timeout
        self._max_retries = getattr(settings, "groq_max_retries", 3)
        self._token_budget = getattr(settings, "groq_token_budget_ceiling", 3500)
        
        # Initialize global class-level concurrency limiter
        max_concurrency = getattr(settings, "groq_max_concurrency", 3)
        if GroqProvider._concurrency_limiter is None:
            GroqProvider._concurrency_limiter = BoundedSemaphore(max_concurrency)

    @classmethod
    def _is_circuit_open(cls) -> bool:
        with cls._circuit_lock:
            now = time.perf_counter()
            return now < cls._circuit_open_until

    @classmethod
    def _record_rate_limit(cls) -> None:
        with cls._circuit_lock:
            cls._consecutive_rate_limits += 1
            if cls._consecutive_rate_limits >= 3:
                # Open circuit for 10 seconds
                cls._circuit_open_until = time.perf_counter() + 10.0
                logger.warning("Groq circuit breaker OPEN for 10s due to consecutive 429s")

    @classmethod
    def _record_success(cls) -> None:
        with cls._circuit_lock:
            cls._consecutive_rate_limits = 0
            cls._circuit_open_until = 0.0

    def _clamp_messages(self, messages: list[dict[str, str]]) -> list[dict[str, str]]:
        """Enforce hard token budget ceiling to prevent Groq TPM blowups."""
        clamped = []
        max_chars = int(self._token_budget * 3.5)
        total_chars = sum(len(m.get("content", "")) for m in messages)

        if total_chars <= max_chars:
            return messages

        # Truncate the largest message (typically the retrieved context in the user prompt)
        for m in messages:
            content = m.get("content", "")
            if len(content) > max_chars // 2:
                reduced = content[: max_chars // 2] + "\n\n... [Evidence clamped to adhere to token budget]"
                clamped.append({**m, "content": reduced})
            else:
                clamped.append(m)
        return clamped

    def _call_api(self, messages: list[dict[str, str]]) -> str:
        if self._is_circuit_open():
            log_event(logger, "llm_circuit_breaker_active", logging.WARNING, provider="groq", model=self.model)
            raise LLMProviderError("AI service is currently rate limited. Please try again in a few moments.")

        messages = self._clamp_messages(messages)
        started = time.perf_counter()
        limiter = GroqProvider._concurrency_limiter or BoundedSemaphore(3)

        # Acquire concurrency token
        with limiter:
            for attempt in range(self._max_retries):
                try:
                    response = httpx.post(
                        GROQ_API_URL,
                        headers={
                            "Authorization": f"Bearer {self._api_key}",
                            "Content-Type": "application/json",
                        },
                        json={
                            "model": self.model,
                            "messages": messages,
                            "temperature": 0.3,
                            "max_tokens": 1200,
                        },
                        timeout=self._timeout,
                    )
                except httpx.TimeoutException as exc:
                    log_event(
                        logger, "llm_api_timeout", logging.ERROR,
                        provider="groq", model=self.model,
                        duration_ms=round((time.perf_counter() - started) * 1000, 2),
                    )
                    raise LLMProviderError("AI service request timed out") from exc
                except httpx.HTTPError as exc:
                    log_event(
                        logger, "llm_api_failed", logging.ERROR,
                        provider="groq", model=self.model,
                        exception_type=type(exc).__name__,
                        duration_ms=round((time.perf_counter() - started) * 1000, 2),
                    )
                    raise LLMProviderError("AI service request failed") from exc

                duration_ms = round((time.perf_counter() - started) * 1000, 2)

                if response.status_code == 401:
                    log_event(
                        logger, "llm_api_auth_failed", logging.ERROR,
                        provider="groq", model=self.model,
                    )
                    raise LLMProviderError("AI service authentication failed. Check GROQ_API_KEY configuration.")

                if response.status_code == 429:
                    self._record_rate_limit()
                    if attempt < self._max_retries - 1:
                        retry_after_str = response.headers.get("retry-after")
                        reset_tokens_str = response.headers.get("x-ratelimit-reset-tokens")
                        
                        # Full jitter exponential backoff: base * 2^attempt + jitter
                        jitter = random.uniform(0.1, 0.4)
                        backoff = (0.75 * (2 ** attempt)) + jitter

                        if retry_after_str:
                            try:
                                backoff = float(retry_after_str) + jitter
                            except ValueError:
                                pass
                        elif reset_tokens_str:
                            try:
                                if reset_tokens_str.endswith("ms"):
                                    backoff = (float(reset_tokens_str.rstrip("ms")) / 1000.0) + jitter
                                elif reset_tokens_str.endswith("s"):
                                    backoff = float(reset_tokens_str.rstrip("s")) + jitter
                            except ValueError:
                                pass

                        wait_time = min(max(backoff, 0.5), 6.0)
                        log_event(
                            logger, "llm_api_rate_limited_retry", logging.WARNING,
                            provider="groq", model=self.model, wait_time=wait_time, attempt=attempt + 1,
                        )
                        time.sleep(wait_time)
                        continue

                    log_event(
                        logger, "llm_api_rate_limited", logging.WARNING,
                        provider="groq", model=self.model, duration_ms=duration_ms,
                    )
                    raise LLMProviderError("AI service rate limited. Please try again shortly.")

                if response.status_code >= 400:
                    log_event(
                        logger, "llm_api_error", logging.ERROR,
                        provider="groq", model=self.model,
                        status_code=response.status_code, duration_ms=duration_ms,
                    )
                    raise LLMProviderError(f"AI service returned HTTP {response.status_code}")
                break

            try:
                data = response.json()
                content = data["choices"][0]["message"]["content"]
                self._record_success()
            except (KeyError, IndexError, ValueError) as exc:
                log_event(
                    logger, "llm_api_invalid_response", logging.ERROR,
                    provider="groq", model=self.model, duration_ms=duration_ms,
                )
                raise LLMProviderError("AI service returned an invalid response") from exc

            log_event(
                logger, "llm_api_completed",
                provider="groq", model=self.model,
                duration_ms=duration_ms,
                response_length=len(content),
            )
            return content
