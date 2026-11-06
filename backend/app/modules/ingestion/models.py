"""Ingestion-owned tables (ING-01..07)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.clock import utcnow_naive
from app.core.db import Base


class ConnectorRecord(Base):
    __tablename__ = "connector"

    id: Mapped[str] = mapped_column(String(26), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    config: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    transform: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    dedupe_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    secret_ref: Mapped[str | None] = mapped_column(String(256), nullable=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False, default=utcnow_naive)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), nullable=False, default=utcnow_naive, onupdate=utcnow_naive
    )
    created_by: Mapped[str] = mapped_column(String(64), nullable=False, default="system")

    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uk_connector_tenant_name"),
        Index("idx_connector_tenant_kind", "tenant_id", "kind"),
    )


class IngestionJob(Base):
    __tablename__ = "ingestion_job"

    id: Mapped[str] = mapped_column(String(26), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(32), nullable=False)
    connector_id: Mapped[str] = mapped_column(String(26), nullable=False)
    dataset_id: Mapped[str] = mapped_column(String(26), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False)
    transform: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    dedupe_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    rows_read: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rows_written: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rows_skipped: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cursor_value: Mapped[str | None] = mapped_column(String(256), nullable=True)
    schema_drift: Mapped[list[dict]] = mapped_column(JSON, nullable=False, default=list)
    error: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False, default=utcnow_naive)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), nullable=False, default=utcnow_naive, onupdate=utcnow_naive
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    created_by: Mapped[str] = mapped_column(String(64), nullable=False, default="system")

    __table_args__ = (
        UniqueConstraint("tenant_id", "idempotency_key", name="uk_ingestion_job_tenant_idem"),
        Index("idx_ingestion_job_tenant_status", "tenant_id", "status", "updated_at"),
    )


class SyncCursor(Base):
    __tablename__ = "sync_cursor"

    id: Mapped[str] = mapped_column(String(26), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(32), nullable=False)
    connector_id: Mapped[str] = mapped_column(String(26), nullable=False)
    dataset_id: Mapped[str] = mapped_column(String(26), nullable=False)
    value: Mapped[str | None] = mapped_column(String(256), nullable=True)
    schema_fields: Mapped[list[dict]] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False, default=utcnow_naive)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), nullable=False, default=utcnow_naive, onupdate=utcnow_naive
    )

    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "connector_id",
            "dataset_id",
            name="uk_sync_cursor_tenant_connector_dataset",
        ),
    )


class QualityRule(Base):
    __tablename__ = "quality_rule"

    id: Mapped[str] = mapped_column(String(26), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    rule_type: Mapped[str] = mapped_column(String(32), nullable=False)
    config: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    severity: Mapped[str] = mapped_column(String(16), nullable=False, default="error")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False, default=utcnow_naive)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), nullable=False, default=utcnow_naive, onupdate=utcnow_naive
    )
    created_by: Mapped[str] = mapped_column(String(64), nullable=False, default="system")

    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uk_quality_rule_tenant_name"),
        Index("idx_quality_rule_tenant_enabled", "tenant_id", "enabled"),
    )


class IngestionDeadLetter(Base):
    """One failed ingestion job captured for manual inspection / replay (ING-09)."""

    __tablename__ = "ingestion_dead_letter"

    id: Mapped[str] = mapped_column(String(26), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(32), nullable=False)
    job_id: Mapped[str] = mapped_column(String(26), nullable=False)
    connector_id: Mapped[str] = mapped_column(String(26), nullable=False)
    reason: Mapped[str] = mapped_column(String(1024), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    replayed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False, default=utcnow_naive)

    __table_args__ = (
        UniqueConstraint("tenant_id", "job_id", name="uk_ingestion_dead_letter_tenant_job"),
        Index("idx_ingestion_dead_letter_tenant_created", "tenant_id", "created_at"),
    )


class QualityResult(Base):
    __tablename__ = "quality_result"

    id: Mapped[str] = mapped_column(String(26), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(32), nullable=False)
    job_id: Mapped[str] = mapped_column(String(26), nullable=False)
    rule_id: Mapped[str | None] = mapped_column(String(26), nullable=True)
    dataset_id: Mapped[str | None] = mapped_column(String(26), nullable=True)
    passed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    checked_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    details: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False, default=utcnow_naive)

    __table_args__ = (Index("idx_quality_result_tenant_job", "tenant_id", "job_id", "created_at"),)
