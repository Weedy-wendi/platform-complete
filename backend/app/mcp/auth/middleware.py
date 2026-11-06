"""Authentication middleware for the MCP ASGI app."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.metrics import MCP_AUTH_FAILURES
from app.mcp.auth.base import AuthError, AuthProvider

PUBLIC_PATHS = {
    "/healthz",
    "/readyz",
    "/metrics",
    "/.well-known/oauth-protected-resource",
}


class AuthMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app: Callable[..., Awaitable[None]],
        *,
        provider: AuthProvider,
        resource_metadata_url: str | None = None,
    ) -> None:
        super().__init__(app)
        self._provider = provider
        self._resource_metadata_url = resource_metadata_url

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if request.url.path in PUBLIC_PATHS or request.method == "OPTIONS":
            return await call_next(request)

        try:
            principal = await self._provider.authenticate(request.headers.get("authorization"))
        except AuthError as exc:
            MCP_AUTH_FAILURES.labels(reason=exc.reason).inc()
            headers = {"WWW-Authenticate": 'Bearer realm="pingce-mcp"'}
            if self._resource_metadata_url and exc.status_code == 401:
                headers["WWW-Authenticate"] = (
                    f'Bearer realm="pingce-mcp", resource_metadata="{self._resource_metadata_url}"'
                )
            body = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {
                    "code": -32000,
                    "message": exc.message,
                    "data": {
                        "code": exc.code,
                        "retryable": False,
                        "trace_id": request.headers.get("x-trace-id"),
                    },
                },
            }
            return JSONResponse(status_code=exc.status_code, content=body, headers=headers)

        from app.core.context import (
            TenantContext,
            reset_principal,
            reset_tenant_context,
            set_principal,
            set_tenant_context,
        )

        token = set_principal(principal)
        tenant_token = set_tenant_context(TenantContext.from_principal(principal))
        try:
            return await call_next(request)
        finally:
            reset_tenant_context(tenant_token)
            reset_principal(token)
