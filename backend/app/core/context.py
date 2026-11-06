"""Request-scoped identity context.

The MCP server is stateless at the protocol level, but each request still needs
an authenticated principal. A context variable keeps that principal available to
tool handlers without passing it through every SDK callback.
"""

from __future__ import annotations

from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

from app.core.errors import TenantRequiredError
from app.core.ids import new_trace_id


@dataclass(frozen=True)
class Principal:
    """Authenticated caller identity."""

    tenant_id: str
    subject: str
    scopes: frozenset[str] = field(default_factory=frozenset)
    auth_method: Literal["api_key", "oauth", "jwt"] = "api_key"
    expires_at: datetime | None = None
    client_id: str | None = None
    api_key_id: int | None = None

    def has_scope(self, scope: str) -> bool:
        return scope in self.scopes

    @property
    def subject_id(self) -> str:
        """Alias used by the identity public contract."""
        return self.subject


@dataclass(frozen=True)
class TenantContext:
    """Tenant-scoped execution context used by services and repositories."""

    tenant_id: str
    subject_id: str
    scopes: frozenset[str] = field(default_factory=frozenset)
    trace_id: str = ""

    def __post_init__(self) -> None:
        if not self.tenant_id:
            raise TenantRequiredError("tenant_id is required")

    @classmethod
    def from_principal(cls, principal: Principal, *, trace_id: str | None = None) -> TenantContext:
        return cls(
            tenant_id=principal.tenant_id,
            subject_id=principal.subject,
            scopes=principal.scopes,
            trace_id=trace_id or new_trace_id(),
        )


_principal: ContextVar[Principal | None] = ContextVar("pingce_principal", default=None)
_tenant_context: ContextVar[TenantContext | None] = ContextVar("pingce_tenant_context", default=None)


def set_principal(principal: Principal) -> Token[Principal | None]:
    return _principal.set(principal)


def reset_principal(token: Token[Principal | None]) -> None:
    _principal.reset(token)


def get_principal() -> Principal:
    principal = _principal.get()
    if principal is None:
        raise TenantRequiredError("No authenticated principal in the current context")
    return principal


def try_get_principal() -> Principal | None:
    return _principal.get()


def set_tenant_context(context: TenantContext) -> Token[TenantContext | None]:
    return _tenant_context.set(context)


def reset_tenant_context(token: Token[TenantContext | None]) -> None:
    _tenant_context.reset(token)


def get_tenant_context() -> TenantContext:
    context = _tenant_context.get()
    if context is None:
        raise TenantRequiredError("No tenant context in the current scope")
    return context


def try_get_tenant_context() -> TenantContext | None:
    return _tenant_context.get()
