"""HTTP middleware: trace propagation, request size limits and metrics."""

from __future__ import annotations

import re
import time

from starlette.datastructures import Headers
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.ids import new_trace_id
from app.core.logging import get_logger
from app.core.metrics import HTTP_REQUEST_DURATION, HTTP_REQUESTS
from app.modules.audit.public import AuditLogEvent, AuditLogWriter

_TRACE_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
_WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
_AUDIT_EXCLUDED_PATHS = ("/healthz", "/readyz", "/metrics")
_AUDIT_MAX_FIELD = 96
_AUDIT_MAX_TRACE = 32

logger = get_logger(__name__)


def _trace_id_from_headers(headers: Headers) -> str:
    candidate = headers.get("x-trace-id", "")
    if candidate and _TRACE_PATTERN.fullmatch(candidate):
        return candidate
    return new_trace_id()


class TraceMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        trace_id = _trace_id_from_headers(request.headers)
        request.state.trace_id = trace_id
        started = time.perf_counter()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
        finally:
            route = request.scope.get("route")
            route_path = getattr(route, "path", None) or "unmatched"
            HTTP_REQUESTS.labels(route=route_path, method=request.method, status=str(status)).inc()
            HTTP_REQUEST_DURATION.labels(route=route_path, method=request.method).observe(time.perf_counter() - started)
        response.headers.setdefault("X-Trace-Id", trace_id)
        return response


def _audit_status(status_code: int) -> str:
    if 200 <= status_code < 400:
        return "success"
    if status_code in {401, 403}:
        return "denied"
    return "error"


def _audit_route(request: Request) -> str:
    route = request.scope.get("route")
    route_path = str(getattr(route, "path", None) or "")
    if not route_path:
        return request.url.path
    # Router prefixes are not part of ``scope["route"].path`` for included
    # routers, so restore the public ``/v1`` prefix for the audit template.
    if request.url.path.startswith("/v1") and not route_path.startswith("/v1"):
        return f"/v1{route_path}"
    return route_path


class WriteAuditMiddleware(BaseHTTPMiddleware):
    """Record one audit event for every mutating ``/v1`` request.

    The writer is optional: when ``app.state.audit_writer`` is unset the
    middleware is a no-op. Events only contain identity, route metadata and the
    response status. Request bodies, query strings, API keys and headers are
    never copied into the audit record.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        writer: AuditLogWriter | None = getattr(request.app.state, "audit_writer", None)
        method = request.method.upper()
        path = request.url.path
        if (
            writer is None
            or method not in _WRITE_METHODS
            or not path.startswith("/v1")
            or path.startswith(_AUDIT_EXCLUDED_PATHS)
        ):
            return await call_next(request)

        try:
            response = await call_next(request)
        except Exception:
            self._record(request, writer, 500, method)
            raise
        self._record(request, writer, response.status_code, method)
        return response

    @staticmethod
    def _record(request: Request, writer: AuditLogWriter, status_code: int, method: str) -> None:
        principal = getattr(request.state, "principal", None)
        tenant_id = str(getattr(principal, "tenant_id", "") or "unknown")
        actor_id = str(getattr(principal, "subject", "") or "anonymous")
        trace_id = str(getattr(request.state, "trace_id", "") or new_trace_id())[:_AUDIT_MAX_TRACE]
        route_path = _audit_route(request)[:_AUDIT_MAX_FIELD]
        event = AuditLogEvent(
            tenant_id=tenant_id[:32],
            actor_id=actor_id[:_AUDIT_MAX_FIELD],
            action=f"{method} {route_path}"[:_AUDIT_MAX_FIELD],
            resource_type="http_route",
            resource_id=route_path,
            trace_id=trace_id,
            status=_audit_status(status_code),
            detail={"status_code": status_code, "method": method},
        )
        try:
            writer.write(event)
        except Exception:  # noqa: BLE001 - auditing must never break a request
            logger.exception("api_audit_write_failed", extra={"trace_id": trace_id})


class RequestSizeLimitMiddleware:
    """Reject oversized JSON requests before they reach the application."""

    def __init__(self, app: ASGIApp, *, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        content_length = headers.get("content-length")
        if content_length is not None:
            try:
                too_large = int(content_length) > self.max_bytes
            except ValueError:
                too_large = False
            if too_large:
                await self._reject(scope, receive, send)
                return

        await self.app(scope, receive, send)

    async def _reject(self, scope: Scope, receive: Receive, send: Send) -> None:
        trace_id = _trace_id_from_headers(Headers(scope=scope))
        body: Message = {
            "code": "REQUEST_TOO_LARGE",
            "message": "Request body exceeds the configured limit",
            "trace_id": trace_id,
            "details": {"limit": self.max_bytes, "retryable": False},
        }
        response = JSONResponse(
            body,
            status_code=413,
            headers={"X-Trace-Id": trace_id},
        )
        await response(scope, receive, send)


__all__ = ["RequestSizeLimitMiddleware", "TraceMiddleware", "WriteAuditMiddleware"]
