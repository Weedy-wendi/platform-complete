"""Shared test fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest
from starlette.testclient import TestClient

from app.core.config import Settings
from app.mcp.server import create_app
from app.modules.audit.public import InMemoryAuditWriter
from app.modules.identity.public import ALLOWED_SCOPES, ApiKeyService, InMemoryApiKeyStore
from tests.support.seeds import build_seeded_services

CONTRACT_PATH = Path(__file__).resolve().parents[2] / "specs" / "001-mcp-server" / "contracts" / "tools.yaml"


@pytest.fixture()
def settings() -> Settings:
    return Settings(
        env="test",
        mcp_contracts_path=CONTRACT_PATH,
        mcp_dns_rebinding_protection=False,
        mcp_redis_url="",
        mcp_api_key_pepper="test-pepper",
        mcp_cursor_secret="test-cursor",
    )


@pytest.fixture()
def api_key_service() -> ApiKeyService:
    return ApiKeyService(InMemoryApiKeyStore(), pepper="test-pepper", key_env="test")


@pytest.fixture()
def issued_key(api_key_service: ApiKeyService):
    return api_key_service.issue(
        tenant_id="tenant-a",
        name="test-key",
        scopes=ALLOWED_SCOPES,
    )


@pytest.fixture()
def audit_writer() -> InMemoryAuditWriter:
    return InMemoryAuditWriter()


@pytest.fixture()
def app(settings: Settings, api_key_service: ApiKeyService, audit_writer: InMemoryAuditWriter):
    return create_app(settings, api_key_service=api_key_service, audit_writer=audit_writer)


@pytest.fixture()
def client(app):
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def auth_headers(issued_key):
    return {
        "Authorization": f"Bearer {issued_key.raw_key}",
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
    }


@pytest.fixture()
def seeded_services():
    return build_seeded_services()


@pytest.fixture()
def seeded_app(
    settings: Settings,
    api_key_service: ApiKeyService,
    audit_writer: InMemoryAuditWriter,
    seeded_services,
):
    return create_app(
        settings,
        api_key_service=api_key_service,
        audit_writer=audit_writer,
        services=seeded_services,
    )


@pytest.fixture()
def seeded_client(seeded_app):
    with TestClient(seeded_app) as test_client:
        yield test_client


def make_headers(raw_key: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {raw_key}",
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
    }
