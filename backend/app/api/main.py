"""FastAPI application factory for the Pingce REST API."""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from dataclasses import replace
from typing import Any

from fastapi import APIRouter, FastAPI
from fastapi.openapi.utils import get_openapi
from sqlalchemy.orm import Session, sessionmaker
from starlette.responses import JSONResponse

from app.api.adapters import CatalogDatasetsAdapter, CatalogProjectsAdapter
from app.api.deps import _DenyAllVerifier
from app.api.errors import install_error_handlers
from app.api.middleware import RequestSizeLimitMiddleware, TraceMiddleware, WriteAuditMiddleware
from app.api.routes import (
    admin,
    datasets,
    datasources,
    evaluators,
    functional,
    gates,
    health,
    identity,
    metrics,
    projects,
    reports,
    runs,
    search,
    share,
    suites,
    targets,
)
from app.api.services import ApiServices, build_api_services
from app.modules.audit.public import AuditLogWriter, SafeAuditLogWriter
from app.modules.catalog.public import CatalogReader, CatalogService
from app.modules.identity.public import (
    ApiKeyAuthenticator,
    ApiKeyService,
    ApiKeyVerifier,
    SqlApiKeyStore,
    SqlTenantStatusChecker,
    TenantStatusChecker,
)

API_VERSION = "1.0.0"
DEFAULT_MAX_REQUEST_BYTES = 1024 * 1024


def _build_authenticator(
    *,
    authenticator: ApiKeyAuthenticator | None,
    api_key_verifier: ApiKeyVerifier | None,
    session_factory: sessionmaker[Session] | None,
    api_key_pepper: str | None,
    key_env: str,
) -> ApiKeyAuthenticator:
    if authenticator is not None:
        return authenticator

    checker: TenantStatusChecker | None = None
    if session_factory is not None:
        checker = SqlTenantStatusChecker(session_factory)

    verifier = api_key_verifier
    if verifier is None and session_factory is not None:
        pepper = api_key_pepper or os.environ.get("PINGCE_API_KEY_PEPPER") or "dev-pepper-change-me"
        service = ApiKeyService(
            SqlApiKeyStore(session_factory),
            pepper=pepper,
            key_env=key_env,
            tenant_status_checker=checker,
        )
        verifier = service

    if verifier is None:
        verifier = _DenyAllVerifier()
    return ApiKeyAuthenticator(verifier, tenant_status_checker=checker)


def _install_openapi(app: FastAPI) -> None:
    def custom_openapi() -> dict[str, Any]:
        if app.openapi_schema:
            return app.openapi_schema
        schema = get_openapi(
            title="Pingce Platform API",
            version=API_VERSION,
            description=(
                "Pingce REST access layer. OpenAPI 3.1 is the only interface contract; "
                "frontend types are generated from this document."
            ),
            routes=app.routes,
        )
        schema["openapi"] = "3.1.0"
        schema["servers"] = [
            {"url": "https://pingce.example.com", "description": "Production"},
            {"url": "http://127.0.0.1:8000", "description": "Local"},
        ]
        components = schema.setdefault("components", {})
        components.setdefault("securitySchemes", {})["bearerAuth"] = {
            "type": "http",
            "scheme": "bearer",
            "description": "API Key `pk_<env>_<key_id>_<secret>`",
        }
        schema["security"] = [{"bearerAuth": []}]
        schema["tags"] = [
            {"name": "health"},
            {"name": "identity"},
            {"name": "projects"},
            {"name": "datasets"},
            {"name": "datasources"},
            {"name": "runs"},
            {"name": "evaluators"},
            {"name": "suites"},
            {"name": "targets"},
            {"name": "gates"},
            {"name": "reports"},
            {"name": "badcases"},
            {"name": "functional"},
            {"name": "admin"},
        ]
        app.openapi_schema = schema
        return schema

    app.openapi = custom_openapi  # type: ignore[method-assign]


def create_api_app(
    *,
    services: ApiServices | None = None,
    catalog: CatalogReader | CatalogService | None = None,
    authenticator: ApiKeyAuthenticator | None = None,
    api_key_verifier: ApiKeyVerifier | None = None,
    session_factory: sessionmaker[Session] | None = None,
    api_key_pepper: str | None = None,
    key_env: str = "dev",
    max_request_bytes: int = DEFAULT_MAX_REQUEST_BYTES,
    cursor_secret: str | None = None,
    cursor_ttl_seconds: int = 900,
    report_share_secret: str | None = None,
    ready_checks: Mapping[str, Callable[[], bool]] | None = None,
    audit_writer: AuditLogWriter | None = None,
) -> FastAPI:
    if max_request_bytes <= 0:
        raise ValueError("max_request_bytes must be positive")

    if services is None:
        active_catalog = catalog
        if active_catalog is None and session_factory is not None:
            active_catalog = CatalogService(session_factory)
        if active_catalog is not None:
            services = build_api_services(
                projects=CatalogProjectsAdapter(active_catalog),
                datasets=CatalogDatasetsAdapter(active_catalog),
                cursor_secret=cursor_secret,
                cursor_ttl_seconds=cursor_ttl_seconds,
                key_env=key_env,
                audit_writer=audit_writer,
            )
        else:
            services = build_api_services(
                cursor_secret=cursor_secret,
                cursor_ttl_seconds=cursor_ttl_seconds,
                key_env=key_env,
                audit_writer=audit_writer,
            )
    elif audit_writer is not None:
        services = replace(services, audit_writer=audit_writer)

    app = FastAPI(
        title="Pingce Platform API",
        version=API_VERSION,
        description="Pingce REST access layer (/v1).",
        docs_url="/docs",
        redoc_url=None,
    )
    app.state.api_services = services
    active_audit_writer = services.audit_writer
    app.state.audit_writer = SafeAuditLogWriter(active_audit_writer) if active_audit_writer is not None else None
    app.state.authenticator = _build_authenticator(
        authenticator=authenticator,
        api_key_verifier=api_key_verifier,
        session_factory=session_factory,
        api_key_pepper=api_key_pepper,
        key_env=key_env,
    )
    app.state.ready_checks = dict(ready_checks or {})
    app.state.max_request_bytes = max_request_bytes
    app.state.report_share_secret = (
        report_share_secret or os.environ.get("PINGCE_REPORT_SHARE_SECRET") or "dev-report-share-change-me"
    )

    install_error_handlers(app)
    app.add_middleware(RequestSizeLimitMiddleware, max_bytes=max_request_bytes)
    app.add_middleware(TraceMiddleware)
    if app.state.audit_writer is not None:
        app.add_middleware(WriteAuditMiddleware)

    app.include_router(health.router)
    app.include_router(metrics.router)

    v1 = APIRouter(prefix="/v1")
    v1.include_router(identity.router)
    v1.include_router(projects.router)
    v1.include_router(datasets.router)
    v1.include_router(datasources.router)
    v1.include_router(runs.router)
    v1.include_router(evaluators.router)
    v1.include_router(suites.router)
    v1.include_router(targets.router)
    v1.include_router(gates.router)
    v1.include_router(reports.router)
    v1.include_router(share.router)
    v1.include_router(search.router)
    v1.include_router(functional.router)
    v1.include_router(admin.router)
    app.include_router(v1)

    @app.get("/v1/openapi.json", include_in_schema=False)
    def exported_openapi() -> JSONResponse:
        return JSONResponse(app.openapi())

    _install_openapi(app)
    return app


__all__ = ["API_VERSION", "DEFAULT_MAX_REQUEST_BYTES", "create_api_app"]
