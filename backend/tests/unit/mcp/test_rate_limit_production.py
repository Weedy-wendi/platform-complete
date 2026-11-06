import pytest

from app.core.config import Settings
from app.core.context import Principal
from app.core.errors import ServiceUnavailableError
from app.mcp.rate_limit import RateLimitService


class BrokenLimiter:
    def consume(self, key: str, *, capacity: int, refill_per_second: float):
        raise RuntimeError("redis down")


def test_production_does_not_fallback_to_local_limiter() -> None:
    settings = Settings(
        env="test",
        mcp_rate_limit_key_per_min=2,
        mcp_rate_limit_tenant_per_min=2,
    )
    service = RateLimitService(settings, BrokenLimiter(), allow_fallback=False)
    with pytest.raises(ServiceUnavailableError):
        service.check(Principal(tenant_id="tenant-a", subject="user:1", client_id="key-1"))


def test_development_falls_back_to_local_limiter() -> None:
    settings = Settings(env="test", mcp_rate_limit_key_per_min=2, mcp_rate_limit_tenant_per_min=2)
    service = RateLimitService(settings, BrokenLimiter(), allow_fallback=True)
    service.check(Principal(tenant_id="tenant-a", subject="user:1", client_id="key-1"))
