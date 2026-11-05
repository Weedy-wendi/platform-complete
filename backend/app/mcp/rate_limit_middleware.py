"""HTTP-level rate limiting middleware.

Rate limits are enforced before JSON-RPC dispatch so an exceeded quota returns
HTTP 429 with ``Retry-After`` (FR-020) instead of a JSON-RPC success envelope.
The request body is buffered only to discover ``tools/call`` names for the
per-tool bucket, then replayed unchanged downstream.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any

from starlette.responses import JSONResponse

from app.core.context import try_get_principal
from app.core.errors import RateLimitedError, ServiceUnavailableError
from app.mcp.rate_limit import RateLimitService

PUBLIC_PATHS = {
    "/healthz",
    "/readyz",
    "/metrics",
    "/.well-known/oauth-protected-resource",
}


class RateLimitMiddleware:
    def __init__(
        self,
        app: Callable[..., Awaitable[None]],
        *,
        service: RateLimitService,
        max_body_bytes: int = 262144,
    ) -> None:
        self._app = app
        self._service = service
        self._max_body_bytes = max_body_bytes

    async def __call__(self, scope: dict[str, Any], receive: Callable, send: Callable) -> None:
        if scope.get("type") != "http" or scope.get("path") in PUBLIC_PATHS:
            await self._app(scope, receive, send)
            return

        principal = try_get_principal()
        if principal is None:
            await self._app(scope, receive, send)
            return

        content_length = _content_length(scope)
        if content_length is not None and content_length > self._max_body_bytes:
            await _too_large(scope, receive, send)
            return

        messages: list[dict[str, Any]] = []
        body = bytearray()
        while True:
            message = await receive()
            messages.append(message)
            if message["type"] == "http.request":
                body.extend(message.get("body", b""))
                if len(body) > self._max_body_bytes:
                    await _too_large(scope, receive, send)
                    return
                if not message.get("more_body", False):
                    break
            elif message["type"] == "http.disconnect":
                break

        tool_name = _tool_name(bytes(body))
        try:
            self._service.check(principal, tool_name)
        except RateLimitedError as exc:
            retry_after = int(exc.details.get("retry_after", 1))
            response = JSONResponse(
                status_code=429,
                content={
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {
                        "code": "RATE_LIMITED",
                        "message": "Rate limited",
                        "retryable": True,
                        "retry_after": retry_after,
                    },
                },
                headers={"Retry-After": str(retry_after)},
            )
            await response(scope, receive, send)
            return
        except ServiceUnavailableError as exc:
            response = JSONResponse(
                status_code=503,
                content={
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {
                        "code": "SERVICE_UNAVAILABLE",
                        "message": exc.message,
                        "retryable": True,
                        "retry_after": 1,
                    },
                },
                headers={"Retry-After": "1"},
            )
            await response(scope, receive, send)
            return

        index = 0

        async def replay() -> dict[str, Any]:
            nonlocal index
            if index < len(messages):
                message = messages[index]
                index += 1
                return message
            return {"type": "http.request", "body": b"", "more_body": False}

        await self._app(scope, replay, send)


async def _too_large(scope: dict[str, Any], receive: Callable, send: Callable) -> None:
    response = JSONResponse(
        status_code=413,
        content={
            "jsonrpc": "2.0",
            "id": None,
            "error": {
                "code": "REQUEST_TOO_LARGE",
                "message": "Request body exceeds the configured limit",
                "retryable": False,
            },
        },
    )
    await response(scope, receive, send)


def _content_length(scope: dict[str, Any]) -> int | None:
    for key, value in scope.get("headers", []):
        if key.lower() == b"content-length":
            try:
                return int(value)
            except (TypeError, ValueError):
                return None
    return None


def _tool_name(body: bytes) -> str | None:
    if not body:
        return None
    try:
        payload = json.loads(body)
    except (ValueError, UnicodeDecodeError):
        return None
    if not isinstance(payload, dict) or payload.get("method") != "tools/call":
        return None
    params = payload.get("params")
    if not isinstance(params, dict):
        return None
    name = params.get("name")
    return name if isinstance(name, str) else None
