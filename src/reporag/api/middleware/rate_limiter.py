"""Per-user API rate limiting middleware."""

from __future__ import annotations

import time
from collections import defaultdict, deque
from collections.abc import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from src.reporag.api.middleware.auth import JWTError, decode_jwt_token
from src.reporag.config import settings


class InMemoryRateLimiter:
    """Sliding-window in-memory rate limiter."""

    def __init__(self, *, limit: int = 60, window_seconds: int = 60) -> None:
        if limit < 1:
            raise ValueError("limit must be at least 1")
        if window_seconds < 1:
            raise ValueError("window_seconds must be at least 1")
        self.limit = limit
        self.window_seconds = window_seconds
        self._requests: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str, *, now: float | None = None) -> bool:
        """Return whether a key is below the request limit."""

        current_time = now if now is not None else time.monotonic()
        history = self._requests[key]
        cutoff = current_time - self.window_seconds
        while history and history[0] <= cutoff:
            history.popleft()
        if len(history) >= self.limit:
            return False
        history.append(current_time)
        return True


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Reject requests that exceed the configured per-user rate limit."""

    def __init__(
        self,
        app: object,
        *,
        limiter: InMemoryRateLimiter | None = None,
        limit: int | None = None,
    ) -> None:
        super().__init__(app)
        self.limiter = limiter or InMemoryRateLimiter(
            limit=limit or settings.api_rate_limit_per_minute
        )

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], object],
    ) -> Response:
        key = rate_limit_key(request)
        if not self.limiter.allow(key):
            request_id = getattr(request.state, "request_id", None)
            return JSONResponse(
                status_code=429,
                content={
                    "error": {
                        "code": "rate_limit_exceeded",
                        "message": "Rate limit exceeded",
                        "request_id": request_id,
                    }
                },
            )
        response = await call_next(request)
        return response


def rate_limit_key(request: Request) -> str:
    """Return a stable rate-limit key for the authenticated user or client IP."""

    authorization = request.headers.get("authorization", "")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() == "bearer" and token:
        try:
            claims = decode_jwt_token(token)
        except JWTError:
            claims = {}
        user_id = claims.get("user_id") or claims.get("sub")
        if user_id:
            return f"user:{user_id}"

    client_host = request.client.host if request.client is not None else "unknown"
    return f"ip:{client_host}"
