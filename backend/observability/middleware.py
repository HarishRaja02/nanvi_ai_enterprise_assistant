from __future__ import annotations

import logging
import re
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from .logging import log_event, reset_request_context, set_request_context

logger = logging.getLogger(__name__)
_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


def _header_id(value: str | None) -> str | None:
    if value and _ID_RE.fullmatch(value):
        return value
    return None


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = _header_id(request.headers.get("X-Request-ID")) or uuid.uuid4().hex
        correlation_id = _header_id(request.headers.get("X-Correlation-ID")) or request_id
        trace_id = uuid.uuid4().hex
        tokens = set_request_context(request_id, correlation_id, trace_id)
        started = time.perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        except Exception as exc:
            log_event(logger, "request_error", logging.ERROR, method=request.method, path=request.url.path,
                      status_code=500, duration_ms=round((time.perf_counter() - started) * 1000, 2),
                      exception_type=type(exc).__name__)
            raise
        finally:
            duration_ms = round((time.perf_counter() - started) * 1000, 2)
            log_event(logger, "request_completed", logging.INFO, method=request.method,
                      path=request.url.path, status_code=status_code, duration_ms=duration_ms)
            # Response headers are added before returning; BaseHTTPMiddleware's response
            # object is available here for normal requests.
            if 'response' in locals():
                response.headers["X-Request-ID"] = request_id
                response.headers["X-Correlation-ID"] = correlation_id
                response.headers["X-Trace-ID"] = trace_id
                response.headers["X-Response-Time-Ms"] = str(duration_ms)
            reset_request_context(tokens)
