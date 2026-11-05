"""Read-only audit queries with tenant filtering and keyset pagination."""

from __future__ import annotations

import base64
import json
from datetime import datetime
from typing import Protocol

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.context import TenantContext
from app.core.errors import InvalidCursorError
from app.core.pagination import Page, clamp_limit
from app.modules.audit.models import AuditLog
from app.modules.audit.writer import AuditLogEvent


class AuditReader(Protocol):
    def query(
        self,
        ctx: TenantContext,
        *,
        actor: str | None = None,
        resource_type: str | None = None,
        since: datetime | None = None,
        cursor: str | None = None,
        limit: int = 20,
    ) -> Page[AuditLogEvent]: ...


def _encode_cursor(row: AuditLog) -> str:
    payload = {"t": row.created_at.isoformat(), "id": row.id}
    return base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode()


def _decode_cursor(cursor: str) -> tuple[datetime, str]:
    try:
        payload = json.loads(base64.urlsafe_b64decode(cursor.encode()))
        return datetime.fromisoformat(payload["t"]), str(payload["id"])
    except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise InvalidCursorError("Invalid audit cursor") from exc


def _to_event(row: AuditLog) -> AuditLogEvent:
    return AuditLogEvent(
        id=row.id,
        tenant_id=row.tenant_id,
        actor_id=row.actor_id,
        action=row.action,
        resource_type=row.resource_type,
        resource_id=row.resource_id,
        trace_id=row.trace_id,
        status=row.status,
        detail=row.detail or {},
        created_at=row.created_at,
    )


class SqlAuditReader:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def query(
        self,
        ctx: TenantContext,
        *,
        actor: str | None = None,
        resource_type: str | None = None,
        since: datetime | None = None,
        cursor: str | None = None,
        limit: int = 20,
    ) -> Page[AuditLogEvent]:
        page_size = clamp_limit(limit, default=20, maximum=100)
        statement = select(AuditLog).where(AuditLog.tenant_id == ctx.tenant_id)
        if actor is not None:
            statement = statement.where(AuditLog.actor_id == actor)
        if resource_type is not None:
            statement = statement.where(AuditLog.resource_type == resource_type)
        if since is not None:
            statement = statement.where(AuditLog.created_at >= since)
        if cursor is not None:
            last_created_at, last_id = _decode_cursor(cursor)
            statement = statement.where(
                or_(
                    AuditLog.created_at < last_created_at,
                    and_(
                        AuditLog.created_at == last_created_at,
                        AuditLog.id < last_id,
                    ),
                )
            )
        statement = statement.order_by(AuditLog.created_at.desc(), AuditLog.id.desc()).limit(page_size + 1)

        with self._session_factory() as session:
            rows = list(session.scalars(statement))
        truncated = len(rows) > page_size
        items = rows[:page_size]
        next_cursor = _encode_cursor(items[-1]) if truncated and items else None
        return Page(items=[_to_event(row) for row in items], next_cursor=next_cursor, truncated=truncated)


class InMemoryAuditReader:
    def __init__(self, events: list[AuditLogEvent]) -> None:
        self._events = list(events)

    def query(
        self,
        ctx: TenantContext,
        *,
        actor: str | None = None,
        resource_type: str | None = None,
        since: datetime | None = None,
        cursor: str | None = None,
        limit: int = 20,
    ) -> Page[AuditLogEvent]:
        page_size = clamp_limit(limit, default=20, maximum=100)
        rows = [event for event in self._events if event.tenant_id == ctx.tenant_id]
        if actor is not None:
            rows = [event for event in rows if event.actor_id == actor]
        if resource_type is not None:
            rows = [event for event in rows if event.resource_type == resource_type]
        if since is not None:
            rows = [event for event in rows if event.created_at >= since]
        rows.sort(key=lambda event: (event.created_at, event.id), reverse=True)
        if cursor is not None:
            last_created_at, last_id = _decode_cursor(cursor)
            rows = [event for event in rows if (event.created_at, event.id) < (last_created_at, last_id)]
        items = rows[:page_size]
        next_cursor = _encode_cursor(_row_for_cursor(items[-1])) if len(rows) > page_size and items else None
        return Page(items=items, next_cursor=next_cursor, truncated=len(rows) > page_size)


def _row_for_cursor(event: AuditLogEvent) -> AuditLog:
    return AuditLog(id=event.id, created_at=event.created_at)
