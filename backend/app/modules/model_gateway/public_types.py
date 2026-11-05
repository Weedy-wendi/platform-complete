"""Model gateway DTOs and provider SPI."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from app.core.context import TenantContext


@dataclass(frozen=True)
class ModelRequest:
    provider: str
    model: str
    messages: list[dict[str, Any]]
    temperature: float = 0.0
    seed: int | None = None
    timeout_seconds: float = 30.0
    max_tokens: int | None = None
    connect_timeout_seconds: float = 5.0
    read_timeout_seconds: float = 30.0


@dataclass(frozen=True)
class ModelResponse:
    text: str
    usage: dict[str, int] = field(default_factory=dict)
    cost_usd: float = 0.0
    raw_ref: str | None = None
    finish_reason: str | None = None


@dataclass(frozen=True)
class ProviderResult:
    text: str
    usage: dict[str, int] = field(default_factory=dict)
    finish_reason: str | None = None
    raw_ref: str | None = None
    raw: Any = None


class RawStore(Protocol):
    """Persist a raw provider payload and return its artifact reference."""

    def put_raw(self, tenant_id: str, call_id: str, payload: bytes) -> str: ...


class ProviderCompletion(Protocol):
    def __call__(self, config: Any, request: ModelRequest) -> ProviderResult: ...


class ModelGateway(Protocol):
    def complete(self, ctx: TenantContext, request: ModelRequest) -> ModelResponse: ...
