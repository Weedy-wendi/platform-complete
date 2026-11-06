"""Service composition for the deployed MCP server.

In development the adapter may run with empty in-memory services. In production
the platform must provide a real read-only `ServiceRegistry`; otherwise the
server would silently return empty data. The factory is selected by a dotted
path so the MCP module never imports business modules directly.
"""

from __future__ import annotations

import importlib
from collections.abc import Callable

from app.core.config import Settings
from app.services import ServiceRegistry, build_empty_services

ServiceFactory = Callable[[Settings], ServiceRegistry]


def load_services_factory(dotted_path: str) -> ServiceFactory:
    module_name, _, attribute = dotted_path.partition(":")
    if not module_name or not attribute:
        raise ValueError("PINGCE_MCP_SERVICES_FACTORY must be a 'module:callable' path")
    module = importlib.import_module(module_name)
    factory = getattr(module, attribute, None)
    if not callable(factory):
        raise ValueError(f"PINGCE_MCP_SERVICES_FACTORY is not callable: {dotted_path}")
    return factory


def build_services_for_settings(
    settings: Settings,
    *,
    explicit: ServiceRegistry | None = None,
) -> ServiceRegistry:
    if explicit is not None:
        return explicit
    configured = settings.mcp_services_factory.strip()
    if configured:
        return load_services_factory(configured)(settings)
    if settings.env.lower() in {"prod", "production"}:
        raise ValueError(
            "PINGCE_MCP_SERVICES_FACTORY is required in production; refusing to fall back to empty in-memory services"
        )
    return build_empty_services()
