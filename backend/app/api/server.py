"""Settings-driven entrypoint for the Pingce REST API.

Run it with::

    uvicorn app.api.server:create_app_from_settings --factory --host 0.0.0.0 --port 8000

The catalog (projects/datasets) and reports are backed by MySQL. The remaining
REST ports use the deterministic in-memory adapters until their module adapters
are wired; the MCP server is the fully SQL-backed read surface.
"""

from __future__ import annotations

import os

from fastapi import FastAPI

from app.api.adapters import (
    CatalogDatasetsAdapter,
    CatalogProjectsAdapter,
    ReportingReportsAdapter,
)
from app.api.main import create_api_app
from app.api.services import build_api_services
from app.core.config import Settings, get_settings
from app.core.db import create_engine_from_dsn, make_session_factory
from app.core.health import check_database
from app.modules.audit.public import SqlAuditLogWriter
from app.modules.catalog.public import CatalogService
from app.modules.reporting.public import ReportService


def create_app_from_settings(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    if not settings.database_url:
        raise RuntimeError("PINGCE_DATABASE_URL is required to start the REST API")

    engine = create_engine_from_dsn(settings.database_url)
    session_factory = make_session_factory(engine)
    catalog = CatalogService(session_factory)
    reports = ReportService(session_factory)
    cursor_secret = settings.mcp_cursor_secret.get_secret_value()
    services = build_api_services(
        projects=CatalogProjectsAdapter(catalog),
        datasets=CatalogDatasetsAdapter(catalog),
        reports=ReportingReportsAdapter(reports),
        cursor_secret=cursor_secret,
        key_env=settings.env,
        audit_writer=SqlAuditLogWriter(session_factory),
    )
    return create_api_app(
        services=services,
        session_factory=session_factory,
        api_key_pepper=settings.mcp_api_key_pepper.get_secret_value(),
        key_env=settings.env,
        cursor_secret=cursor_secret,
        report_share_secret=os.environ.get("PINGCE_REPORT_SHARE_SECRET"),
        ready_checks={"database": lambda: check_database(engine)},
    )


__all__ = ["create_app_from_settings"]
