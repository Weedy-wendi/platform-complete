"""Audit log writer tests (AUD-01 dependency for IDN-06)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.core.db import make_session_factory
from app.core.metrics import AUDIT_WRITE_FAILED
from app.modules.audit.models import AuditLog
from app.modules.audit.writer import (
    AuditLogEvent,
    InMemoryAuditLogWriter,
    SafeAuditLogWriter,
    SqlAuditLogWriter,
    sanitize_detail,
)


def test_sanitize_detail_removes_secrets_and_pii() -> None:
    sanitized = sanitize_detail(
        {
            "password": "hunter2",
            "api_key": "pk_test_abcdefgh",
            "note": "alice@example.com 13800138000",
            "nested": [{"token": "abc"}],
        }
    )
    assert sanitized["password"] == "[REDACTED]"
    assert sanitized["api_key"] == "[REDACTED]"
    assert sanitized["nested"][0]["token"] == "[REDACTED]"
    assert "alice@example.com" not in sanitized["note"]
    assert "13800138000" not in sanitized["note"]


def test_in_memory_writer_records_events() -> None:
    writer = InMemoryAuditLogWriter()
    event = AuditLogEvent(
        tenant_id="tenant-a",
        actor_id="user:1",
        action="identity.login",
        resource_type="user",
        resource_id="user:1",
        trace_id="trace-1",
    )
    writer.write(event)
    assert writer.events == [event]


def test_sql_writer_persists_sanitized_event() -> None:
    engine = create_engine("sqlite://")
    AuditLog.__table__.create(engine)
    factory = make_session_factory(engine)
    writer = SqlAuditLogWriter(factory)
    try:
        writer.write(
            AuditLogEvent(
                tenant_id="tenant-a",
                actor_id="user:1",
                action="identity.key.issued",
                resource_type="api_key",
                resource_id="key-1",
                trace_id="trace-1",
                detail={"raw_key": "pk_test_supersecret", "note": "alice@example.com"},
            )
        )
        with Session(engine) as session:
            assert session.scalar(select(func.count()).select_from(AuditLog)) == 1
            row = session.scalar(select(AuditLog))
            assert row is not None
            assert row.actor_id == "user:1"
            assert row.detail["raw_key"] == "[REDACTED]"
            assert "alice@example.com" not in row.detail["note"]
    finally:
        engine.dispose()


def test_event_has_ulid_and_utc_timestamp() -> None:
    event = AuditLogEvent(
        tenant_id="tenant-a",
        actor_id="user:1",
        action="identity.login",
        resource_type="user",
        resource_id="user:1",
        trace_id="trace-1",
    )
    assert len(event.id) == 26
    assert isinstance(event.created_at, datetime)
    assert event.created_at.tzinfo is None


def test_safe_writer_swallows_failure_and_increments_metric() -> None:
    class FailingWriter:
        def write(self, event: AuditLogEvent) -> None:
            raise RuntimeError("audit db unavailable")

    before = AUDIT_WRITE_FAILED._value.get()  # type: ignore[attr-defined]
    SafeAuditLogWriter(FailingWriter()).write(
        AuditLogEvent(
            tenant_id="tenant-a",
            actor_id="user:1",
            action="identity.login",
            resource_type="user",
            resource_id="user:1",
            trace_id="trace-1",
        )
    )
    assert AUDIT_WRITE_FAILED._value.get() == before + 1  # type: ignore[attr-defined]
