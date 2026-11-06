"""MCP API-key auth tests for tenant status (IDN-11)."""

from __future__ import annotations

import pytest

from app.mcp.auth.api_key import ApiKeyAuthProvider
from app.mcp.auth.base import AuthError
from app.modules.identity.api_key import ApiKeyService, InMemoryApiKeyStore


class ToggleTenantStatus:
    def __init__(self) -> None:
        self.active = True

    def is_active(self, tenant_id: str) -> bool:
        return self.active


async def test_mcp_provider_rejects_disabled_tenant() -> None:
    checker = ToggleTenantStatus()
    service = ApiKeyService(
        InMemoryApiKeyStore(),
        pepper="test-pepper",
        tenant_status_checker=checker,
    )
    issued = service.issue(tenant_id="tenant-a", name="ci", scopes={"mcp:projects:read"})
    provider = ApiKeyAuthProvider(service)

    principal = await provider.authenticate(f"Bearer {issued.raw_key}")
    assert principal.tenant_id == "tenant-a"

    checker.active = False
    with pytest.raises(AuthError):
        await provider.authenticate(f"Bearer {issued.raw_key}")
