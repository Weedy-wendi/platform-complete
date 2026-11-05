"""OAuth switch test with a fake provider (SC-009, T054)."""

from __future__ import annotations

from starlette.testclient import TestClient

from app.core.config import Settings
from app.core.context import Principal
from app.mcp.auth.base import AuthError
from app.mcp.server import create_app
from app.modules.audit.public import InMemoryAuditWriter
from app.modules.identity.public import ALLOWED_SCOPES, ApiKeyService, InMemoryApiKeyStore


class FakeOAuthProvider:
    """Stands in for an IdP-backed resource server."""

    async def authenticate(self, authorization: str | None) -> Principal:
        if not authorization:
            raise AuthError("Missing Authorization header", reason="missing")
        return Principal(
            tenant_id="tenant-a",
            subject="oauth-user",
            scopes=frozenset(ALLOWED_SCOPES),
            auth_method="oauth",
            client_id="client-1",
        )


def _oauth_settings(**overrides) -> Settings:
    values = {
        "env": "test",
        "mcp_auth_mode": "oauth",
        "mcp_oauth_issuer": "https://issuer.example.com",
        "mcp_oauth_audience": "https://pingce.example.com/mcp",
        "mcp_oauth_jwks_url": "https://issuer.example.com/.well-known/jwks.json",
        "mcp_oauth_resource_metadata_url": "https://pingce.example.com/.well-known/oauth-protected-resource",
        "mcp_dns_rebinding_protection": False,
        "mcp_redis_url": "",
        "mcp_api_key_pepper": "test-pepper",
        "mcp_cursor_secret": "test-cursor",
    }
    values.update(overrides)
    return Settings(**values)


def _headers() -> dict[str, str]:
    return {
        "Authorization": "Bearer fake-oauth-token",
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
    }


def test_oauth_mode_works_without_tool_changes(monkeypatch, settings) -> None:
    monkeypatch.setattr("app.mcp.server.build_auth_provider", lambda _s, _svc: FakeOAuthProvider())
    api_key_service = ApiKeyService(InMemoryApiKeyStore(), pepper="test-pepper", key_env="test")
    app = create_app(
        _oauth_settings(mcp_contracts_path=settings.mcp_contracts_path),
        api_key_service=api_key_service,
        audit_writer=InMemoryAuditWriter(),
    )
    with TestClient(app) as client:
        listed = client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
            headers=_headers(),
        )
        assert listed.status_code == 200
        assert len(listed.json()["result"]["tools"]) == 10

        called = client.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": "list_projects", "arguments": {}},
            },
            headers=_headers(),
        )
        assert called.status_code == 200
        assert called.json()["result"]["isError"] is False


def test_oauth_metadata_endpoint(monkeypatch, settings) -> None:
    monkeypatch.setattr("app.mcp.server.build_auth_provider", lambda _s, _svc: FakeOAuthProvider())
    api_key_service = ApiKeyService(InMemoryApiKeyStore(), pepper="test-pepper", key_env="test")
    app = create_app(
        _oauth_settings(mcp_contracts_path=settings.mcp_contracts_path),
        api_key_service=api_key_service,
        audit_writer=InMemoryAuditWriter(),
    )
    with TestClient(app) as client:
        response = client.get("/.well-known/oauth-protected-resource")
    assert response.status_code == 200
    assert response.json()["authorization_servers"] == ["https://issuer.example.com"]
