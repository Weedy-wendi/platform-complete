"""Audit reader tests (AUD-03)."""

from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy import create_engine

from app.core.context import TenantContext
from app.core.db import make_session_factory
from app.core.errors import InvalidCursorError
from app.modules.audit.models import AuditLog
from app.modules.audit.reader import InMemoryAuditReader, SqlAuditReader
from app.modules.audit.writer import AuditLogEvent, SqlAuditLogWriter


def _event(tenant: str, event_id: str, created_at: datetime, **overrides) -> AuditLogEvent:
    return AuditLogEvent(
        id=event_id,
        tenant_id=tenant,
        actor_id=overrides.get("actor_id", "user:1"),
        action=overrides.get("action", "identity.login"),
        resource_type=overrides.get("resource_type", "user"),
        resource_id=overrides.get("resource_id", "user:1"),
        trace_id=overrides.get("trace_id", "trace-1"),
        status=overrides.get("status", "success"),
        detail=overrides.get("detail", {}),
        created_at=created_at,
    )


@pytest.fixture()
def factory():
    engine = create_engine("sqlite://")
    AuditLog.__table__.create(engine)
    try:
        yield make_session_factory(engine)
    finally:
        engine.dispose()


@pytest.fixture()
def reader(factory) -> SqlAuditReader:
    return SqlAuditReader(factory)


@pytest.fixture()
def ctx() -> TenantContext:
    return TenantContext(tenant_id="tenant-a", subject_id="admin", scopes=frozenset(), trace_id="trace")


def _seed(factory) -> None:
    writer = SqlAuditLogWriter(factory)
    writer.write(_event("tenant-a", "e1", datetime(2026, 1, 1, 12, 0, 0), actor_id="user:1"))
    writer.write(_event("tenant-a", "e2", datetime(2026, 1, 2, 12, 0, 0), actor_id="user:2"))
    writer.write(_event("tenant-a", "e3", datetime(2026, 1, 3, 12, 0, 0), actor_id="user:1"))
    writer.write(_event("tenant-b", "e4", datetime(2026, 1, 4, 12, 0, 0), actor_id="user:1"))


def test_reader_filters_by_tenant_and_orders_newest_first(factory, reader, ctx) -> None:
    _seed(factory)
    page = reader.query(ctx)
    assert [event.id for event in page.items] == ["e3", "e2", "e1"]
    assert all(event.tenant_id == "tenant-a" for event in page.items)


def test_reader_filters_actor_resource_and_since(factory, reader, ctx) -> None:
    _seed(factory)
    assert [event.id for event in reader.query(ctx, actor="user:1").items] == ["e3", "e1"]
    assert [event.id for event in reader.query(ctx, resource_type="user").items] == ["e3", "e2", "e1"]
    assert [event.id for event in reader.query(ctx, since=datetime(2026, 1, 2)).items] == ["e3", "e2"]


def test_reader_keyset_pagination(factory, reader, ctx) -> None:
    _seed(factory)
    first = reader.query(ctx, limit=2)
    assert [event.id for event in first.items] == ["e3", "e2"]
    assert first.truncated is True
    assert first.next_cursor

    second = reader.query(ctx, limit=2, cursor=first.next_cursor)
    assert [event.id for event in second.items] == ["e1"]
    assert second.truncated is False
    assert second.next_cursor is None


def test_reader_rejects_invalid_cursor(reader, ctx) -> None:
    with pytest.raises(InvalidCursorError):
        reader.query(ctx, cursor="not-a-cursor")


def test_in_memory_reader_matches_tenant_filter() -> None:
    events = [
        _event("tenant-a", "e1", datetime(2026, 1, 1, 12, 0, 0)),
        _event("tenant-b", "e2", datetime(2026, 1, 2, 12, 0, 0)),
    ]
    page = InMemoryAuditReader(events).query(
        TenantContext(tenant_id="tenant-a", subject_id="admin", scopes=frozenset(), trace_id="t")
    )
    assert [event.id for event in page.items] == ["e1"]
