from pathlib import Path

from starlette.testclient import TestClient

from app.core.config import Settings
from app.mcp.rate_limit import LocalTokenBucket
from app.mcp.server import create_app
from app.modules.audit.public import InMemoryAuditWriter
from app.modules.identity.public import ALLOWED_SCOPES, ApiKeyService, InMemoryApiKeyStore

CONTRACT = Path(__file__).resolve().parents[4] / "specs" / "001-mcp-server" / "contracts" / "tools.yaml"


def _call(client, headers, method, request_id, params=None):
    payload = {"jsonrpc": "2.0", "id": request_id, "method": method}
    if params is not None:
        payload["params"] = params
    return client.post("/mcp", json=payload, headers=headers)


def test_resource_methods_are_rate_limited() -> None:
    settings = Settings(
        env="test",
        mcp_contracts_path=CONTRACT,
        mcp_dns_rebinding_protection=False,
        mcp_redis_url="",
        mcp_rate_limit_key_per_min=2,
        mcp_rate_limit_tenant_per_min=2,
    )
    service = ApiKeyService(InMemoryApiKeyStore(), pepper="test-pepper", key_env="test")
    issued = service.issue(tenant_id="tenant-a", name="rate-limit", scopes=ALLOWED_SCOPES)
    app = create_app(
        settings,
        api_key_service=service,
        audit_writer=InMemoryAuditWriter(),
        rate_limiter=LocalTokenBucket(),
    )
    headers = {
        "Authorization": f"Bearer {issued.raw_key}",
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
    }
    with TestClient(app) as client:
        _call(
            client,
            headers,
            "initialize",
            1,
            {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "pytest", "version": "0"},
            },
        )
        first = _call(client, headers, "resources/templates/list", 2)
        second = _call(client, headers, "resources/templates/list", 3)
    assert first.status_code == 200
    assert "result" in first.json()
    assert second.status_code == 429
    assert "error" in second.json()
    assert int(second.headers["Retry-After"]) >= 1
