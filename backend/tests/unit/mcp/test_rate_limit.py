import pytest

from app.core.config import Settings
from app.core.context import Principal
from app.core.errors import RateLimitedError
from app.mcp.rate_limit import LocalTokenBucket, RateLimitService


def _settings() -> Settings:
    return Settings(
        env="test",
        mcp_rate_limit_key_per_min=2,
        mcp_rate_limit_tenant_per_min=10,
        mcp_rate_limit_heavy_per_min=1,
        mcp_rate_limit_heavy_tools=("preview_samples",),
    )


def _principal() -> Principal:
    return Principal(tenant_id="tenant-a", subject="user:1", client_id="key-1")


def test_local_bucket_blocks_after_capacity() -> None:
    bucket = LocalTokenBucket()
    assert bucket.consume("k", capacity=2, refill_per_second=0).allowed is True
    assert bucket.consume("k", capacity=2, refill_per_second=0).allowed is True
    decision = bucket.consume("k", capacity=2, refill_per_second=0)
    assert decision.allowed is False
    assert decision.retry_after >= 1


def test_service_enforces_key_and_heavy_limits() -> None:
    service = RateLimitService(_settings(), LocalTokenBucket())
    principal = _principal()
    service.check(principal)
    service.check(principal)
    with pytest.raises(RateLimitedError):
        service.check(principal)


def test_heavy_tool_limit() -> None:
    service = RateLimitService(_settings(), LocalTokenBucket())
    principal = _principal()
    service.check(principal, "preview_samples")
    with pytest.raises(RateLimitedError):
        service.check(principal, "preview_samples")


class BrokenLimiter:
    def consume(self, key: str, *, capacity: int, refill_per_second: float):
        raise RuntimeError("redis down")


def test_fallback_when_limiter_fails() -> None:
    service = RateLimitService(_settings(), BrokenLimiter())
    service.check(_principal())
