"""Functional test models (FUN-01)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.clock import utcnow_naive
from app.core.db import Base


class FunctionalTestCase(Base):
    __tablename__ = "test_case"

    id: Mapped[str] = mapped_column(String(26), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    steps: Mapped[list[dict]] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False, default=utcnow_naive)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), nullable=False, default=utcnow_naive, onupdate=utcnow_naive
    )
    created_by: Mapped[str] = mapped_column(String(64), nullable=False, default="system")

    __table_args__ = (
        UniqueConstraint("tenant_id", "name", "version", name="uk_test_case_tenant_name_version"),
        Index("idx_test_case_tenant_name", "tenant_id", "name", "version"),
    )


class FunctionalTestSuite(Base):
    __tablename__ = "test_suite"

    id: Mapped[str] = mapped_column(String(26), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    case_refs: Mapped[list[dict]] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False, default=utcnow_naive)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), nullable=False, default=utcnow_naive, onupdate=utcnow_naive
    )
    created_by: Mapped[str] = mapped_column(String(64), nullable=False, default="system")

    __table_args__ = (
        UniqueConstraint("tenant_id", "name", "version", name="uk_test_suite_tenant_name_version"),
        Index("idx_test_suite_tenant_name", "tenant_id", "name", "version"),
    )


class TestRun(Base):
    __tablename__ = "test_run"

    id: Mapped[str] = mapped_column(String(26), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(32), nullable=False)
    suite_id: Mapped[str] = mapped_column(String(26), nullable=False)
    suite_version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    browser_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False, default=utcnow_naive)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    created_by: Mapped[str] = mapped_column(String(64), nullable=False, default="system")

    __table_args__ = (Index("idx_test_run_tenant_suite", "tenant_id", "suite_id", "created_at"),)


class TestStep(Base):
    __tablename__ = "test_step"

    id: Mapped[str] = mapped_column(String(26), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(32), nullable=False)
    run_id: Mapped[str] = mapped_column(String(26), nullable=False)
    case_id: Mapped[str] = mapped_column(String(26), nullable=False)
    step_index: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    kind: Mapped[str] = mapped_column(String(24), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    assertion: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    evidence_ref: Mapped[str | None] = mapped_column(String(64), nullable=True)
    evidence_refs: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    error: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False, default=utcnow_naive)

    __table_args__ = (Index("idx_test_step_tenant_run", "tenant_id", "run_id", "step_index"),)


class AssertionRecord(Base):
    __tablename__ = "assertion"

    id: Mapped[str] = mapped_column(String(26), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(32), nullable=False)
    step_id: Mapped[str] = mapped_column(String(26), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    config: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    passed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    expected: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    actual: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    message: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False, default=utcnow_naive)

    __table_args__ = (Index("idx_assertion_tenant_step", "tenant_id", "step_id"),)


class FunctionalDeadLetter(Base):
    """A step that still failed after the single automatic retry (FUN-08)."""

    __tablename__ = "functional_dead_letter"

    id: Mapped[str] = mapped_column(String(26), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(32), nullable=False)
    run_id: Mapped[str] = mapped_column(String(26), nullable=False)
    step_id: Mapped[str] = mapped_column(String(26), nullable=False)
    case_id: Mapped[str] = mapped_column(String(26), nullable=False)
    reason: Mapped[str] = mapped_column(String(1024), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    replayed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False, default=utcnow_naive)

    __table_args__ = (
        UniqueConstraint("tenant_id", "run_id", "step_id", name="uk_functional_dead_letter_tenant_run_step"),
        Index("idx_functional_dead_letter_tenant_created", "tenant_id", "created_at"),
    )


class VisualDiff(Base):
    __tablename__ = "visual_diff"

    id: Mapped[str] = mapped_column(String(26), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(32), nullable=False)
    run_id: Mapped[str | None] = mapped_column(String(26), nullable=True)
    step_id: Mapped[str | None] = mapped_column(String(26), nullable=True)
    expected_ref: Mapped[str] = mapped_column(String(64), nullable=False)
    actual_ref: Mapped[str] = mapped_column(String(64), nullable=False)
    diff_ref: Mapped[str | None] = mapped_column(String(64), nullable=True)
    threshold: Mapped[float] = mapped_column(Float, nullable=False, default=0.01)
    mismatch_ratio: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    passed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False, default=utcnow_naive)

    __table_args__ = (Index("idx_visual_diff_tenant_run", "tenant_id", "run_id"),)
