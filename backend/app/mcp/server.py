"""MCP Streamable HTTP application assembly."""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any

import redis as redis_lib
from mcp import types
from mcp.server import Server
from mcp.server.streamable_http import TransportSecuritySettings
from mcp.shared.exceptions import MCPError
from sqlalchemy import text
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from app.core.config import Settings, get_settings
from app.core.context import Principal, get_principal
from app.core.db import create_engine_from_dsn, create_readonly_engine_from_dsn, make_session_factory
from app.core.errors import AppError
from app.core.ids import new_trace_id
from app.core.kill_switch import KILL_SWITCHES
from app.core.logging import get_logger
from app.core.metrics import (
    MCP_TOOL_CALLS,
    MCP_TOOL_DURATION,
    MCP_TOOL_RESULT_BYTES,
    metrics_payload,
)
from app.core.tracing import configure_tracing, get_tracer
from app.mcp.audit import McpAuditService
from app.mcp.auth.factory import build_auth_provider
from app.mcp.auth.middleware import AuthMiddleware
from app.mcp.rate_limit import LocalTokenBucket, RateLimiter, RateLimitService, RedisTokenBucket
from app.mcp.rate_limit_middleware import RateLimitMiddleware
from app.mcp.registry import ToolCallContext, ToolRegistry
from app.mcp.resources import read_resource
from app.mcp.tools import register_default_handlers
from app.modules.audit.public import AuditWriter, InMemoryAuditWriter, SqlAuditWriter
from app.modules.identity.public import (
    ApiKeyService,
    ApiKeyStore,
    InMemoryApiKeyStore,
    SqlApiKeyStore,
    SqlTenantStatusChecker,
)
from app.services import ServiceRegistry
from app.services.factory import build_services_for_settings

logger = get_logger(__name__)


def _is_prod(settings: Settings) -> bool:
    return settings.env.lower() in {"prod", "production"}


def _build_api_key_service(settings: Settings) -> tuple[ApiKeyService, Any]:
    store: ApiKeyStore
    checker: SqlTenantStatusChecker | None = None
    if settings.mcp_db_dsn:
        engine = create_readonly_engine_from_dsn(settings.mcp_db_dsn)
        factory = make_session_factory(engine)
        store = SqlApiKeyStore(factory)
        # Legacy MCP-only tenants may not have a tenant row yet; existing rows
        # with status=disabled/deleted still reject authentication.
        checker = SqlTenantStatusChecker(factory, allow_missing=True)
    else:
        if _is_prod(settings):
            raise ValueError("MCP_DB_DSN is required in production")
        engine = None
        store = InMemoryApiKeyStore()
    service = ApiKeyService(
        store,
        pepper=settings.mcp_api_key_pepper.get_secret_value(),
        key_env=settings.env,
        tenant_status_checker=checker,
    )
    return service, engine


def _build_audit_writer(settings: Settings) -> tuple[AuditWriter, Any]:
    if settings.mcp_audit_dsn:
        engine = create_engine_from_dsn(settings.mcp_audit_dsn)
        return SqlAuditWriter(make_session_factory(engine)), engine
    if _is_prod(settings):
        raise ValueError("MCP_AUDIT_DSN is required in production")
    return InMemoryAuditWriter(), None


def _build_rate_limiter(settings: Settings) -> RateLimiter:
    if settings.mcp_redis_url:
        try:
            client = redis_lib.Redis.from_url(settings.mcp_redis_url, decode_responses=True)
            client.ping()
            return RedisTokenBucket(client)
        except Exception:
            if _is_prod(settings):
                raise
            logger.warning("redis_unavailable_using_local_rate_limiter")
    elif _is_prod(settings):
        raise ValueError("MCP_REDIS_URL is required in production")
    return LocalTokenBucket()


def create_app(
    settings: Settings | None = None,
    *,
    api_key_service: ApiKeyService | None = None,
    audit_writer: AuditWriter | None = None,
    rate_limiter: RateLimiter | None = None,
    services: ServiceRegistry | None = None,
) -> Starlette:
    settings = settings or get_settings()
    configure_tracing("pingce-mcp")
    tracer = get_tracer("pingce-mcp")

    if api_key_service is None:
        api_key_service, engine = _build_api_key_service(settings)
    else:
        engine = None
    if audit_writer is None:
        audit_writer, audit_engine = _build_audit_writer(settings)
    else:
        audit_engine = None
    audit = McpAuditService(audit_writer)
    rate_limit = RateLimitService(
        settings,
        rate_limiter or _build_rate_limiter(settings),
        allow_fallback=not _is_prod(settings),
    )
    auth_provider = build_auth_provider(settings, api_key_service)

    registry = ToolRegistry.from_contract(
        settings.mcp_contracts_path,
        max_result_bytes=settings.mcp_max_result_bytes,
    )
    services = build_services_for_settings(settings, explicit=services)
    register_default_handlers(registry, services=services, settings=settings)

    async def on_list_tools(ctx: Any, params: Any) -> types.ListToolsResult:
        return types.ListToolsResult(tools=registry.list_tools())

    async def on_call_tool(ctx: Any, params: types.CallToolRequestParams) -> types.CallToolResult:
        principal: Principal = get_principal()
        name = params.name
        arguments = params.arguments or {}
        trace_id = new_trace_id()
        started = time.perf_counter()
        span = tracer.start_span("mcp.tool.call")
        span.set_attribute("mcp.tool.name", name)
        span.set_attribute("tenant.id", principal.tenant_id)
        result: types.CallToolResult
        status = "ok"
        error_code: str | None = None
        try:
            KILL_SWITCHES.require("mcp")
            result = await registry.call_tool_with_timeout(
                name,
                arguments,
                ToolCallContext(
                    principal=principal,
                    tool_name=name,
                    tool_version=registry.version,
                    trace_id=trace_id,
                    request_id=getattr(ctx, "request_id", None),
                ),
                settings.mcp_tool_timeout_seconds,
            )
            if result.is_error:
                status = "error"
                if isinstance(result.structured_content, dict):
                    error_code = result.structured_content.get("code")
        except AppError as exc:
            status = "error"
            error_code = exc.code
            result = types.CallToolResult(
                is_error=True,
                content=[types.TextContent(text=exc.message)],
                structured_content={
                    "code": exc.code,
                    "message": exc.message,
                    "retryable": exc.retryable,
                    "trace_id": trace_id,
                    **exc.details,
                },
            )
        except Exception:
            status = "error"
            error_code = "INTERNAL"
            logger.exception("mcp_tool_internal_error", extra={"tool": name, "trace_id": trace_id})
            result = types.CallToolResult(
                is_error=True,
                content=[types.TextContent(text="Internal error")],
                structured_content={"code": "INTERNAL", "retryable": True, "trace_id": trace_id},
            )

        latency_ms = int((time.perf_counter() - started) * 1000)
        payload = result.model_dump(mode="json")
        result_bytes = len(json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8"))
        MCP_TOOL_CALLS.labels(tool=name, status=status).inc()
        MCP_TOOL_DURATION.labels(tool=name).observe(latency_ms / 1000.0)
        MCP_TOOL_RESULT_BYTES.labels(tool=name).observe(result_bytes)
        span.set_attribute("mcp.tool.status", status)
        span.set_attribute("mcp.tool.latency_ms", latency_ms)
        span.end()
        await asyncio.to_thread(
            audit.record,
            principal=principal,
            tool_name=name,
            tool_version=registry.version,
            status=status,
            latency_ms=latency_ms,
            result_bytes=result_bytes,
            trace_id=trace_id,
            error_code=error_code,
        )
        return result

    async def on_list_resources(ctx: Any, params: Any) -> types.ListResourcesResult:
        return types.ListResourcesResult(resources=[])

    async def on_list_resource_templates(ctx: Any, params: Any) -> types.ListResourceTemplatesResult:
        return types.ListResourceTemplatesResult(resource_templates=registry.list_resource_templates())

    async def on_read_resource(ctx: Any, params: types.ReadResourceRequestParams) -> types.ReadResourceResult:
        principal = get_principal()
        try:
            return await asyncio.to_thread(read_resource, params.uri, services=services, principal=principal)
        except AppError as exc:
            # Resources are not tool results, so surface a JSON-RPC error with
            # the same stable code/retryability contract (FR-021).
            raise MCPError(
                -32000,
                exc.message,
                data={
                    "code": exc.code,
                    "retryable": exc.retryable,
                    "trace_id": new_trace_id(),
                    **exc.details,
                },
            ) from exc
        except Exception as exc:
            trace_id = new_trace_id()
            logger.exception("mcp_resource_internal_error", extra={"trace_id": trace_id})
            raise MCPError(
                -32603,
                "Internal error",
                data={"code": "INTERNAL", "retryable": True, "trace_id": trace_id},
            ) from exc

    server = Server(
        "pingce-mcp",
        version="0.1.0",
        on_list_tools=on_list_tools,
        on_call_tool=on_call_tool,
        on_list_resources=on_list_resources,
        on_list_resource_templates=on_list_resource_templates,
        on_read_resource=on_read_resource,
    )

    async def healthz(request: Request) -> JSONResponse:
        return JSONResponse({"status": "ok"})

    async def readyz(request: Request) -> JSONResponse:
        state = request.app.state
        if state.engine is not None:
            try:
                with state.engine.connect() as conn:
                    conn.execute(text("SELECT 1"))
            except Exception:
                return JSONResponse({"status": "not_ready", "dependency": "mysql"}, status_code=503)
        if state.audit_engine is not None:
            try:
                with state.audit_engine.connect() as conn:
                    conn.execute(text("SELECT 1"))
            except Exception:
                return JSONResponse({"status": "not_ready", "dependency": "mysql-audit"}, status_code=503)
        if state.redis_client is not None:
            try:
                state.redis_client.ping()
            except Exception:
                return JSONResponse({"status": "not_ready", "dependency": "redis"}, status_code=503)
        return JSONResponse({"status": "ready"})

    async def metrics(request: Request) -> Response:
        payload, content_type = metrics_payload()
        return Response(content=payload, media_type=content_type)

    async def oauth_metadata(request: Request) -> JSONResponse:
        if settings.mcp_auth_mode != "oauth":
            return JSONResponse({"error": "not_found"}, status_code=404)
        return JSONResponse(
            {
                "resource": settings.mcp_oauth_resource_metadata_url or "",
                "authorization_servers": [settings.mcp_oauth_issuer],
                "bearer_methods_supported": ["header"],
                "scopes_supported": sorted(
                    {
                        "mcp:projects:read",
                        "mcp:datasets:read",
                        "mcp:eval:read",
                        "mcp:eval:read_content",
                        "mcp:badcases:read",
                        "mcp:gate:read",
                    }
                ),
            }
        )

    security = TransportSecuritySettings(
        enable_dns_rebinding_protection=settings.mcp_dns_rebinding_protection,
        allowed_hosts=list(settings.mcp_allowed_hosts),
    )
    app = server.streamable_http_app(
        stateless_http=True,
        json_response=True,
        streamable_http_path="/mcp",
        transport_security=security,
        max_request_body_size=settings.mcp_max_request_bytes,
        custom_starlette_routes=[
            Route("/healthz", healthz, methods=["GET"]),
            Route("/readyz", readyz, methods=["GET"]),
            Route("/metrics", metrics, methods=["GET"]),
            Route("/.well-known/oauth-protected-resource", oauth_metadata, methods=["GET"]),
        ],
    )
    app.state.settings = settings
    app.state.api_key_service = api_key_service
    app.state.audit_writer = audit_writer
    app.state.rate_limit = rate_limit
    app.state.registry = registry
    app.state.services = services
    app.state.engine = engine
    app.state.audit_engine = audit_engine
    app.state.redis_client = getattr(rate_limiter, "_client", None)
    # Auth runs first (outer) so the rate limiter can read the principal.
    app.add_middleware(
        RateLimitMiddleware,
        service=rate_limit,
        max_body_bytes=settings.mcp_max_request_bytes,
    )
    app.add_middleware(
        AuthMiddleware,
        provider=auth_provider,
        resource_metadata_url=settings.mcp_oauth_resource_metadata_url,
    )
    return app


def run(host: str = "0.0.0.0", port: int = 8765) -> None:
    import uvicorn

    # Stop accepting new requests and give in-flight calls up to 30s (T063).
    uvicorn.run(create_app(), host=host, port=port, timeout_graceful_shutdown=30)
