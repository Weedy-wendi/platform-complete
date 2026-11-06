"""Token-bucket rate limiting with a local fallback."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Protocol

from app.core.config import Settings
from app.core.context import Principal
from app.core.errors import RateLimitedError, ServiceUnavailableError
from app.core.metrics import MCP_RATE_LIMITED


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    remaining: int = 0
    retry_after: int = 0


class RateLimiter(Protocol):
    def consume(self, key: str, *, capacity: int, refill_per_second: float) -> RateLimitDecision: ...


class LocalTokenBucket:
    def __init__(self) -> None:
        self._state: dict[str, tuple[float, float]] = {}

    def consume(self, key: str, *, capacity: int, refill_per_second: float) -> RateLimitDecision:
        now = time.monotonic()
        tokens, last = self._state.get(key, (float(capacity), now))
        elapsed = max(0.0, now - last)
        tokens = min(float(capacity), tokens + elapsed * refill_per_second)
        if tokens >= 1.0:
            tokens -= 1.0
            self._state[key] = (tokens, now)
            return RateLimitDecision(True, int(tokens))
        retry_after = max(1, int((1.0 - tokens) / max(refill_per_second, 0.001)))
        self._state[key] = (tokens, now)
        return RateLimitDecision(False, 0, retry_after)


class RedisTokenBucket:
    _SCRIPT = """
    local key = KEYS[1]
    local capacity = tonumber(ARGV[1])
    local refill = tonumber(ARGV[2])
    local now = tonumber(ARGV[3])
    local cost = tonumber(ARGV[4])
    local ttl = tonumber(ARGV[5])
    local data = redis.call('HMGET', key, 'tokens', 'ts')
    local tokens = tonumber(data[1])
    local ts = tonumber(data[2])
    if tokens == nil then tokens = capacity end
    if ts == nil then ts = now end
    local elapsed = math.max(0, now - ts)
    tokens = math.min(capacity, tokens + elapsed * refill)
    local allowed = tokens >= cost
    if allowed then tokens = tokens - cost end
    redis.call('HMSET', key, 'tokens', tokens, 'ts', now)
    redis.call('EXPIRE', key, ttl)
    local retry = 0
    if not allowed then retry = math.ceil((cost - tokens) / math.max(refill, 0.001)) end
    return {allowed and 1 or 0, math.floor(tokens), retry}
    """

    def __init__(self, client: object) -> None:
        self._client = client

    def consume(self, key: str, *, capacity: int, refill_per_second: float) -> RateLimitDecision:
        result = self._client.eval(  # type: ignore[attr-defined]
            self._SCRIPT,
            1,
            key,
            capacity,
            refill_per_second,
            time.time(),
            1,
            120,
        )
        allowed, remaining, retry_after = result
        return RateLimitDecision(bool(allowed), int(remaining), int(retry_after))


class RateLimitService:
    def __init__(
        self,
        settings: Settings,
        limiter: RateLimiter,
        fallback: RateLimiter | None = None,
        *,
        allow_fallback: bool = True,
    ) -> None:
        self._settings = settings
        self._limiter = limiter
        self._fallback = fallback or LocalTokenBucket()
        self._allow_fallback = allow_fallback

    def _consume(self, key: str, capacity: int, per_minute: int) -> RateLimitDecision:
        refill = per_minute / 60.0
        try:
            return self._limiter.consume(key, capacity=capacity, refill_per_second=refill)
        except Exception as exc:
            if not self._allow_fallback:
                raise ServiceUnavailableError("Rate limiter is unavailable") from exc
            return self._fallback.consume(key, capacity=capacity, refill_per_second=refill)

    def check(self, principal: Principal, tool_name: str | None = None) -> None:
        key_id = principal.client_id or principal.subject
        decisions = [
            self._consume(
                f"mcp:rl:key:{key_id}",
                self._settings.mcp_rate_limit_key_per_min,
                self._settings.mcp_rate_limit_key_per_min,
            ),
            self._consume(
                f"mcp:rl:tenant:{principal.tenant_id}",
                self._settings.mcp_rate_limit_tenant_per_min,
                self._settings.mcp_rate_limit_tenant_per_min,
            ),
        ]
        if tool_name and tool_name in self._settings.mcp_rate_limit_heavy_tools:
            decisions.append(
                self._consume(
                    f"mcp:rl:heavy:{principal.tenant_id}:{key_id}:{tool_name}",
                    self._settings.mcp_rate_limit_heavy_per_min,
                    self._settings.mcp_rate_limit_heavy_per_min,
                )
            )
        denied = [decision for decision in decisions if not decision.allowed]
        if denied:
            MCP_RATE_LIMITED.labels(scope="key").inc()
            raise RateLimitedError(max(decision.retry_after for decision in denied))
