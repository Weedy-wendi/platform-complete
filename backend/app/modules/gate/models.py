"""Gate and rule models plus immutable evaluation results."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Float, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.clock import utcnow_naive
from app.core.db import Base


class Gate(Base):
    __tablename__ = "gate"

    id: Mapped[str] = mapped_column(String(26), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(32), nullable=False)
    suite_id: Mapped[str] = mapped_column(String(26), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    rules_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    baseline_run_id: Mapped[str | None] = mapped_column(String(26), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False, default=utcnow_naive)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), nullable=False, default=utcnow_naive, onupdate=utcnow_naive
    )
    created_by: Mapped[str] = mapped_column(String(64), nullable=False, default="system")

    __table_args__ = (
        UniqueConstraint("tenant_id", "suite_id", "name", name="uk_gate_tenant_suite_name"),
        Index("idx_gate_tenant_suite", "tenant_id", "suite_id"),
    )


class GateRuleRecord(Base):
    __tablename__ = "gate_rule"

    id: Mapped[str] = mapped_column(String(26), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(32), nullable=False)
    gate_id: Mapped[str] = mapped_column(String(26), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    kind: Mapped[str] = mapped_column(String(24), nullable=False)
    metric: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    operator: Mapped[str] = mapped_column(String(8), nullable=False, default="gte")
    threshold: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    baseline_run_id: Mapped[str | None] = mapped_column(String(26), nullable=True)
    min_samples: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False, default=utcnow_naive)

    __table_args__ = (
        UniqueConstraint("gate_id", "name", name="uk_gate_rule_gate_name"),
        Index("idx_gate_rule_tenant_gate", "tenant_id", "gate_id"),
    )


class GateResultRecord(Base):
    __tablename__ = "gate_result"

    id: Mapped[str] = mapped_column(String(26), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(32), nullable=False)
    gate_id: Mapped[str] = mapped_column(String(26), nullable=False)
    suite_id: Mapped[str] = mapped_column(String(26), nullable=False)
    run_id: Mapped[str] = mapped_column(String(26), nullable=False)
    manifest_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    passed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    rules: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False, default=utcnow_naive)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False, default=utcnow_naive)

    __table_args__ = (
        Index("idx_gate_result_tenant_suite_run", "tenant_id", "suite_id", "run_id", "evaluated_at"),
        Index("idx_gate_result_tenant_gate_run", "tenant_id", "gate_id", "run_id", "evaluated_at"),
    )
