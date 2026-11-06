"""Default tool handlers.

All ten read-only tools are wired here. Handlers only call application
services; they never issue SQL or implement retrieval/gate logic.
"""

from __future__ import annotations

from app.core.config import Settings
from app.mcp.cursor import CursorCodec
from app.mcp.registry import ToolRegistry
from app.mcp.tools import badcases, datasets, evaluation, projects
from app.services import ServiceRegistry, build_empty_services

DEFAULT_CURSOR_SECRET = "dev-cursor-change-me"


def register_default_handlers(
    registry: ToolRegistry,
    *,
    services: ServiceRegistry | None = None,
    settings: Settings | None = None,
    cursor_codec: CursorCodec | None = None,
) -> None:
    services = services or build_empty_services()
    if cursor_codec is None:
        if settings is not None:
            secret = settings.mcp_cursor_secret.get_secret_value()
            ttl_seconds = settings.mcp_cursor_ttl_seconds
        else:
            secret = DEFAULT_CURSOR_SECRET
            ttl_seconds = 900
        cursor_codec = CursorCodec(secret, ttl_seconds=ttl_seconds)
    projects.register(registry, services, cursor_codec)
    datasets.register(registry, services, cursor_codec)
    evaluation.register(registry, services, cursor_codec)
    badcases.register(registry, services, cursor_codec)


__all__ = ["register_default_handlers"]
