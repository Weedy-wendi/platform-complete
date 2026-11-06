"""Jobs: state machine, idempotency, retry, DLQ, scheduler lock, progress."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.clock import utcnow_naive
from app.core.db import Base


class Job(Base):
    __tablename__ = "job"

    id: Mapped[str] = mapped_column(String(26), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(32), nullable=False)
    job_type: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False, default=utcnow_naive)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), nullable=False, default=utcnow_naive, onupdate=utcnow_naive
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    created_by: Mapped[str] = mapped_column(String(64), nullable=False, default="system")

    __table_args__ = (
        UniqueConstraint("tenant_id", "idempotency_key", name="uk_job_tenant_idempotency"),
        Index("idx_job_tenant_status", "tenant_id", "status", "updated_at"),
    )


class JobEvent(Base):
    __tablename__ = "job_event"

    id: Mapped[str] = mapped_column(String(26), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(32), nullable=False)
    job_id: Mapped[str] = mapped_column(String(26), nullable=False)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False, default=utcnow_naive)

    __table_args__ = (Index("idx_job_event_tenant_job", "tenant_id", "job_id", "created_at"),)


class DeadLetterTask(Base):
    __tablename__ = "dead_letter_task"

    id: Mapped[str] = mapped_column(String(26), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(32), nullable=False)
    job_id: Mapped[str] = mapped_column(String(26), nullable=False)
    job_type: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    error: Mapped[str] = mapped_column(String(1024), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False, default=utcnow_naive)

    __table_args__ = (Index("idx_dlq_tenant_status", "tenant_id", "status", "created_at"),)


class IdempotencyKey(Base):
    __tablename__ = "idempotency_key"

    id: Mapped[str] = mapped_column(String(26), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(32), nullable=False)
    key: Mapped[str] = mapped_column(String(128), nullable=False)
    job_id: Mapped[str] = mapped_column(String(26), nullable=False)
    item_id: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False, default=utcnow_naive)

    __table_args__ = (
        UniqueConstraint("tenant_id", "key", name="uk_idempotency_tenant_key"),
        Index("idx_idempotency_tenant_job", "tenant_id", "job_id"),
    )
