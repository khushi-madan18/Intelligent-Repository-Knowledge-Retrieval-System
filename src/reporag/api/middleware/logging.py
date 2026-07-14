"""Request ID and structured logging middleware."""

from __future__ import annotations

import json
import logging
import time
import uuid
from collections.abc import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

REQUEST_ID_HEADER = "X-Request-ID"
logger = logging.getLogger("reporag.api")


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Attach a request ID to request state and response headers."""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], object],
    ) -> Response:
        request_id = request.headers.get(REQUEST_ID_HEADER) or str(uuid.uuid4())
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers[REQUEST_ID_HEADER] = request_id
        return response


class StructuredLoggingMiddleware(BaseHTTPMiddleware):
    """Log every request as one JSON object."""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], object],
    ) -> Response:
        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        request_id = getattr(request.state, "request_id", None)
        log_payload = {
            "event": "http_request",
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "duration_ms": duration_ms,
            "client": request.client.host if request.client is not None else None,
        }
        logger.info(json.dumps(log_payload, separators=(",", ":")))
        return response
