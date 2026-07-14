"""Tests for API middleware."""

from __future__ import annotations

import asyncio
import json
import logging

from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from src.reporag.api.middleware.error_handler import error_response
from src.reporag.api.middleware.logging import (
    REQUEST_ID_HEADER,
    RequestIDMiddleware,
    StructuredLoggingMiddleware,
)
from src.reporag.api.middleware.rate_limiter import (
    InMemoryRateLimiter,
    RateLimitMiddleware,
    rate_limit_key,
)
from src.reporag.api.middleware.auth import create_access_token
from src.reporag.api.main import create_app


def request_for(
    path: str = "/api/v1/health",
    *,
    headers: list[tuple[bytes, bytes]] | None = None,
) -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": path,
        "headers": headers or [],
        "scheme": "http",
        "server": ("testserver", 80),
        "client": ("127.0.0.1", 50000),
        "root_path": "",
        "app": create_app(),
    }
    return Request(scope)


async def ok_response(request: Request) -> Response:
    return JSONResponse({"ok": True})


def test_rate_limiter_returns_429_after_limit() -> None:
    async def run() -> tuple[int, int]:
        middleware = RateLimitMiddleware(
            object(),
            limiter=InMemoryRateLimiter(limit=1),
        )
        request = request_for()
        first = await middleware.dispatch(request, ok_response)
        second = await middleware.dispatch(request, ok_response)
        return first.status_code, second.status_code

    assert asyncio.run(run()) == (200, 429)


def test_rate_limiter_uses_per_user_key() -> None:
    token = create_access_token("user-1", email="khushi@example.com")
    request = request_for(headers=[(b"authorization", f"Bearer {token}".encode())])

    assert rate_limit_key(request) == "user:user-1"


def test_request_id_middleware_sets_response_header() -> None:
    async def run() -> str:
        middleware = RequestIDMiddleware(object())
        request = request_for(
            headers=[(REQUEST_ID_HEADER.lower().encode(), b"req-123")]
        )
        response = await middleware.dispatch(request, ok_response)
        return response.headers[REQUEST_ID_HEADER]

    assert asyncio.run(run()) == "req-123"


def test_structured_logging_emits_json(caplog) -> None:
    async def run() -> None:
        middleware = StructuredLoggingMiddleware(object())
        request = request_for()
        request.state.request_id = "req-123"
        with caplog.at_level(logging.INFO, logger="reporag.api"):
            await middleware.dispatch(request, ok_response)

    asyncio.run(run())
    payload = json.loads(caplog.records[0].message)

    assert payload["event"] == "http_request"
    assert payload["request_id"] == "req-123"
    assert payload["method"] == "GET"
    assert payload["path"] == "/api/v1/health"
    assert payload["status_code"] == 200


def test_error_response_has_clean_shape_without_stack_trace() -> None:
    request = request_for()
    request.state.request_id = "req-123"

    response = error_response(
        request,
        status_code=500,
        code="internal_server_error",
        message="Internal server error",
    )
    payload = json.loads(response.body)

    assert response.status_code == 500
    assert payload == {
        "error": {
            "code": "internal_server_error",
            "message": "Internal server error",
            "request_id": "req-123",
        }
    }
    assert "Traceback" not in response.body.decode()


def test_app_installs_middleware() -> None:
    middleware_classes = {middleware.cls for middleware in create_app().user_middleware}

    assert RateLimitMiddleware in middleware_classes
    assert StructuredLoggingMiddleware in middleware_classes
    assert RequestIDMiddleware in middleware_classes
