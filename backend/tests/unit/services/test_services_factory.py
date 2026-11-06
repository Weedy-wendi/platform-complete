"""Production service composition tests (T074)."""

from __future__ import annotations

import pytest

from app.core.config import Settings
from app.mcp.rate_limit import LocalTokenBucket
from app.mcp.server import create_app
from app.modules.audit.public import InMemoryAuditWriter
from app.services.factory import build_services_for_settings, load_services_factory


def _prod_settings(**overrides) -> Settings:
    values = {
        "env": "prod",
        "mcp_api_key_pepper": "real-pepper",
        "mcp_cursor_secret": "real-cursor",
        "mcp_db_dsn": "mysql+pymysql://ro:pass@db:3306/pingce",
        "mcp_audit_dsn": "mysql+pymysql://audit:pass@db:3306/pingce",
        "mcp_redis_url": "redis://redis:6379/0",
    }
    values.update(overrides)
    return Settings(**values)


def test_explicit_registry_wins(seeded_services) -> None:
    settings = Settings(env="test")
    assert build_services_for_settings(settings, explicit=seeded_services) is seeded_services


def test_dotted_factory_is_loaded() -> None:
    settings = Settings(
        env="test",
        mcp_services_factory="tests.support.factory:build_test_services",
    )
    registry = build_services_for_settings(settings)
    assert [project.id for project in registry.projects.list_projects("tenant-a")] == [
        "prj_1",
        "prj_2",
        "prj_3",
    ]


def test_production_requires_a_factory() -> None:
    with pytest.raises(ValueError, match="PINGCE_MCP_SERVICES_FACTORY"):
        build_services_for_settings(_prod_settings())


def test_invalid_factory_path_is_rejected() -> None:
    with pytest.raises(ValueError):
        load_services_factory("not-a-dotted-path")


def test_create_app_refuses_empty_services_in_production(api_key_service) -> None:
    with pytest.raises(ValueError, match="PINGCE_MCP_SERVICES_FACTORY"):
        create_app(
            _prod_settings(),
            api_key_service=api_key_service,
            audit_writer=InMemoryAuditWriter(),
            rate_limiter=LocalTokenBucket(),
        )
