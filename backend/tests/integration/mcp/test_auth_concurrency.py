import asyncio

import pytest

from app.mcp.auth.api_key import ApiKeyAuthProvider
from app.modules.identity.public import ALLOWED_SCOPES


@pytest.mark.asyncio
async def test_parallel_authentication(api_key_service) -> None:
    issued = api_key_service.issue(tenant_id="tenant-a", name="concurrent", scopes=ALLOWED_SCOPES)
    provider = ApiKeyAuthProvider(api_key_service)
    principals = await asyncio.gather(*[provider.authenticate(f"Bearer {issued.raw_key}") for _ in range(20)])
    assert len(principals) == 20
    assert all(principal.tenant_id == "tenant-a" for principal in principals)
