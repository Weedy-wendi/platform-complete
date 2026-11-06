"""Rate-limit behavior at the HTTP boundary (FR-020, T065)."""

from __future__ import annotations

from pathlib import Path

from starlette.testclient import TestClient

from app.core.config import Settings
from app.mcp.server import create_app
from app.modules.audit.public import InMemoryAuditWriter
from app.modules.identity.public import ALLOWED_SCOPES, ApiKeyService, InMemoryApiKeyStore

CONTRACT = Path(__file__).resolve().parents[4] / "specs" / "001-mcp-server" / "contracts" / "tools.yaml"


def _settings(**overrides) -> Settings:
    values = {
        "env": "test",
        "mcp_contracts_path": CONTRACT,
        "mcp_dns_rebinding_protection": False,
        "mcp_redis_url": "",
        "mcp_api_key_pepper": "test-pepper",
        "mcp_cursor_secret": "test-cursor",
    }
    values.update(overrides)
    return Settings(**values)


def _headers(raw_key: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {raw_key}",
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
    }


def _list(client, headers, request_id=1):
    return client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": request_id, "method": "tools/list", "params": {}},
        headers=headers,
    )


def _call(client, headers, name, arguments, request_id=1):
    return client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        },
        headers=headers,
    )


def test_default_thresholds_match_spec() -> None:
    settings = _settings()
    assert settings.mcp_rate_limit_key_per_min == 120
    assert settings.mcp_rate_limit_tenant_per_min == 600
    assert settings.mcp_rate_limit_heavy_per_min == 30


def test_key_limit_returns_429_with_retry_after() -> None:
    settings = _settings(mcp_rate_limit_key_per_min=2, mcp_rate_limit_tenant_per_min=100)
    service = ApiKeyService(InMemoryApiKeyStore(), pepper="test-pepper", key_env="test")
    issued = service.issue(tenant_id="tenant-a", name="key-limit", scopes=ALLOWED_SCOPES)
    app = create_app(settings, api_key_service=service, audit_writer=InMemoryAuditWriter())
    with TestClient(app) as client:
        responses = [_list(client, _headers(issued.raw_key), index) for index in range(3)]
    assert [response.status_code for response in responses] == [200, 200, 429]
    assert int(responses[2].headers["Retry-After"]) >= 1


def test_tenant_limit_spans_multiple_keys() -> None:
    settings = _settings(mcp_rate_limit_key_per_min=100, mcp_rate_limit_tenant_per_min=2)
    service = ApiKeyService(InMemoryApiKeyStore(), pepper="test-pepper", key_env="test")
    key_a = service.issue(tenant_id="tenant-a", name="a", scopes=ALLOWED_SCOPES)
    key_b = service.issue(tenant_id="tenant-a", name="b", scopes=ALLOWED_SCOPES)
    app = create_app(settings, api_key_service=service, audit_writer=InMemoryAuditWriter())
    with TestClient(app) as client:
        first = _list(client, _headers(key_a.raw_key), 1)
        second = _list(client, _headers(key_b.raw_key), 2)
        third = _list(client, _headers(key_a.raw_key), 3)
    assert first.status_code == 200
    assert second.status_code == 200
    assert third.status_code == 429


def test_heavy_tool_has_its_own_bucket() -> None:
    settings = _settings(
        mcp_rate_limit_key_per_min=100,
        mcp_rate_limit_tenant_per_min=100,
        mcp_rate_limit_heavy_per_min=2,
    )
    service = ApiKeyService(InMemoryApiKeyStore(), pepper="test-pepper", key_env="test")
    issued = service.issue(tenant_id="tenant-a", name="heavy", scopes=ALLOWED_SCOPES)
    app = create_app(settings, api_key_service=service, audit_writer=InMemoryAuditWriter())
    with TestClient(app) as client:
        responses = [
            _call(client, _headers(issued.raw_key), "preview_samples", {"dataset_id": "ds_1"}, index)
            for index in range(3)
        ]
    assert [response.status_code for response in responses] == [200, 200, 429]
    assert responses[2].headers["Retry-After"]
