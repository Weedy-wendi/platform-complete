"""Append-only audit writers."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol

from sqlalchemy.orm import Session, sessionmaker

from app.core.clock import utcnow_naive
from app.core.ids import new_ulid
from app.core.logging import get_logger, redact_text
from app.core.metrics import AUDIT_WRITE_FAILED
from app.modules.audit.models import AuditLog, McpToolCall

logger = get_logger(__name__)


@dataclass(frozen=True)
class AuditEvent:
    tenant_id: str
    api_key_id: int
    tool_name: str
    tool_version: str
    status: str
    latency_ms: int
    result_bytes: int
    trace_id: str
    error_code: str | None = None
    client_name: str | None = None
    created_at: datetime = field(default_factory=utcnow_naive)
    extra: dict[str, Any] = field(default_factory=dict)


class AuditWriter(Protocol):
    def write(self, event: AuditEvent) -> None: ...


class InMemoryAuditWriter:
    def __init__(self) -> None:
        self.events: list[AuditEvent] = []

    def write(self, event: AuditEvent) -> None:
        self.events.append(event)


class SqlAuditWriter:
    """Writes to the primary audit DSN, never to the business read replica."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def write(self, event: AuditEvent) -> None:
        with self._session_factory() as session:
            session.add(
                McpToolCall(
                    tenant_id=event.tenant_id,
                    api_key_id=event.api_key_id,
                    client_name=event.client_name,
                    tool_name=event.tool_name,
                    tool_version=event.tool_version,
                    status=event.status,
                    error_code=event.error_code,
                    latency_ms=event.latency_ms,
                    result_bytes=event.result_bytes,
                    trace_id=event.trace_id,
                    created_at=event.created_at,
                )
            )
            session.commit()


_SENSITIVE_KEYS = frozenset(
    {
        "password",
        "passwd",
        "secret",
        "token",
        "authorization",
        "api_key",
        "raw_key",
        "private_key",
    }
)


def sanitize_detail(value: Any) -> Any:
    """Recursively remove PII/secrets from audit detail."""
    if isinstance(value, dict):
        return {
            key: "[REDACTED]" if key.lower() in _SENSITIVE_KEYS else sanitize_detail(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [sanitize_detail(item) for item in value]
    if isinstance(value, tuple):
        return [sanitize_detail(item) for item in value]
    if isinstance(value, str):
        return redact_text(value)
    return value


@dataclass(frozen=True)
class AuditLogEvent:
    tenant_id: str
    actor_id: str
    action: str
    resource_type: str
    resource_id: str
    trace_id: str
    status: str = "success"
    detail: dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=new_ulid)
    created_at: datetime = field(default_factory=utcnow_naive)


class AuditLogWriter(Protocol):
    def write(self, event: AuditLogEvent) -> None: ...


class InMemoryAuditLogWriter:
    def __init__(self) -> None:
        self.events: list[AuditLogEvent] = []

    def write(self, event: AuditLogEvent) -> None:
        self.events.append(event)


class SqlAuditLogWriter:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def write(self, event: AuditLogEvent) -> None:
        with self._session_factory() as session:
            session.add(
                AuditLog(
                    id=event.id,
                    tenant_id=event.tenant_id,
                    actor_id=event.actor_id,
                    action=event.action,
                    resource_type=event.resource_type,
                    resource_id=event.resource_id,
                    trace_id=event.trace_id,
                    status=event.status,
                    detail=sanitize_detail(event.detail),
                    created_at=event.created_at,
                )
            )
            session.commit()


class SafeAuditLogWriter:
    """Never let an audit failure break the caller's request."""

    def __init__(self, writer: AuditLogWriter) -> None:
        self._writer = writer

    def write(self, event: AuditLogEvent) -> None:
        try:
            self._writer.write(event)
        except Exception:
            AUDIT_WRITE_FAILED.inc()
            logger.exception(
                "audit_write_failed",
                extra={"action": event.action, "trace_id": event.trace_id},
            )
