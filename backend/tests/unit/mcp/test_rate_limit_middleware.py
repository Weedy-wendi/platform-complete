"""Rate-limit middleware dependency failure (T084)."""

from __future__ import annotations

from typing import Any

from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from app.core.config import Settings
from app.core.context import Principal, reset_principal, set_principal
from app.mcp.rate_limit import RateLimitService
from app.mcp.rate_limit_middleware import RateLimitMiddleware


class BrokenLimiter:
    def consume(self, key: str, *, capacity: int, refill_per_second: float) -> Any:
        raise RuntimeError("redis down")


class PrincipalMiddleware:
    def __init__(self, app: Any) -> None:
        self._app = app

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        token = set_principal(Principal(tenant_id="tenant-a", subject="user:1", client_id="key-1"))
        try:
            await self._app(scope, receive, send)
        finally:
            reset_principal(token)


async def _endpoint(request):
    return JSONResponse({"ok": True})


def test_limiter_outage_returns_503() -> None:
    settings = Settings(env="test")
    service = RateLimitService(settings, BrokenLimiter(), allow_fallback=False)
    app = Starlette(routes=[Route("/mcp", _endpoint, methods=["POST"])])
    app.add_middleware(RateLimitMiddleware, service=service, max_body_bytes=1024)
    app.add_middleware(PrincipalMiddleware)

    with TestClient(app) as client:
        response = client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
        )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "SERVICE_UNAVAILABLE"
    assert response.headers["Retry-After"] == "1"
