"""Request-body size guard (T079)."""

from __future__ import annotations

from pathlib import Path

from starlette.testclient import TestClient

from app.core.config import Settings
from app.mcp.server import create_app
from app.modules.audit.public import InMemoryAuditWriter
from app.modules.identity.public import ALLOWED_SCOPES, ApiKeyService, InMemoryApiKeyStore

CONTRACT = Path(__file__).resolve().parents[4] / "specs" / "001-mcp-server" / "contracts" / "tools.yaml"


def test_oversized_body_is_rejected_with_413() -> None:
    settings = Settings(
        env="test",
        mcp_contracts_path=CONTRACT,
        mcp_max_request_bytes=128,
        mcp_dns_rebinding_protection=False,
        mcp_redis_url="",
        mcp_api_key_pepper="test-pepper",
        mcp_cursor_secret="test-cursor",
    )
    service = ApiKeyService(InMemoryApiKeyStore(), pepper="test-pepper", key_env="test")
    issued = service.issue(tenant_id="tenant-a", name="body", scopes=ALLOWED_SCOPES)
    app = create_app(settings, api_key_service=service, audit_writer=InMemoryAuditWriter())
    body = '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{"pad":"' + ("a" * 500) + '"}}'
    headers = {
        "Authorization": f"Bearer {issued.raw_key}",
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
    }
    with TestClient(app) as client:
        response = client.post("/mcp", content=body, headers=headers)
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "REQUEST_TOO_LARGE"
