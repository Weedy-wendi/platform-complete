"""MCP resource dispatcher."""

from __future__ import annotations

from mcp import types

from app.core.context import Principal
from app.core.errors import NotFoundError
from app.mcp.resources.datasets import read_dataset_schema
from app.mcp.resources.reports import read_run_resource
from app.services import ServiceRegistry, build_empty_services

__all__ = ["read_resource", "placeholder_contents"]


def placeholder_contents(uri: str) -> types.ReadResourceResult:
    """Kept for backwards compatibility with early-phase callers."""
    return types.ReadResourceResult(
        contents=[
            types.TextResourceContents(
                uri=uri,
                mime_type="text/plain",
                text="Resource not found.",
            )
        ]
    )


def read_resource(
    uri: str,
    *,
    services: ServiceRegistry | None = None,
    principal: Principal,
) -> types.ReadResourceResult:
    services = services or build_empty_services()
    result = read_dataset_schema(uri, services=services, principal=principal)
    if result is not None:
        return result
    result = read_run_resource(uri, services=services, principal=principal)
    if result is not None:
        return result
    raise NotFoundError("Resource not found", uri=uri)
