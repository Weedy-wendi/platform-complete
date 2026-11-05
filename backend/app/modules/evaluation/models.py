"""Evaluation persistence models.

Evaluator versions, suite versions, targets, baselines and completed runs are
immutable. Runs own their manifest snapshot so historical results remain
reproducible even when configuration changes.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Float, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.clock import utcnow_naive
from app.core.db import Base


class Evaluator(Base):
    __tablename__ = "evaluator"

    id: Mapped[str] = mapped_column(String(26), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    kind: Mapped[str] = mapped_column(String(32), nullable=False, default="rule")
    latest_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False, default=utcnow_naive)
    created_by: Mapped[str] = mapped_column(String(64), nullable=False, default="system")

    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uk_evaluator_tenant_name"),
        Index("idx_evaluator_tenant_kind", "tenant_id", "kind"),
    )


class EvaluatorVersion(Base):
    __tablename__ = "evaluator_version"

    id: Mapped[str] = mapped_column(String(26), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(32), nullable=False)
    evaluator_id: Mapped[str] = mapped_column(String(26), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    config: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    config_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False, default=utcnow_naive)
    created_by: Mapped[str] = mapped_column(String(64), nullable=False, default="system")

    __table_args__ = (
        UniqueConstraint("tenant_id", "evaluator_id", "version", name="uk_eval_version_tenant_evaluator_version"),
        Index("idx_eval_version_tenant_evaluator", "tenant_id", "evaluator_id", "version"),
    )


class Metric(Base):
    __tablename__ = "metric"

    id: Mapped[str] = mapped_column(String(26), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    direction: Mapped[str] = mapped_column(String(32), nullable=False, default="higher_is_better")
    evaluator_id: Mapped[str | None] = mapped_column(String(26), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False, default=utcnow_naive)

    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uk_metric_tenant_name"),
        Index("idx_metric_tenant_direction", "tenant_id", "direction"),
    )


class EvalSuite(Base):
    __tablename__ = "eval_suite"

    id: Mapped[str] = mapped_column(String(26), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    latest_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False, default=utcnow_naive)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), nullable=False, default=utcnow_naive, onupdate=utcnow_naive
    )
    created_by: Mapped[str] = mapped_column(String(64), nullable=False, default="system")

    __table_args__ = (UniqueConstraint("tenant_id", "name", name="uk_suite_tenant_name"),)


class SuiteVersion(Base):
    __tablename__ = "suite_version"

    id: Mapped[str] = mapped_column(String(26), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(32), nullable=False)
    suite_id: Mapped[str] = mapped_column(String(26), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    evaluator_versions: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    metric_configs: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False, default=utcnow_naive)
    created_by: Mapped[str] = mapped_column(String(64), nullable=False, default="system")

    __table_args__ = (
        UniqueConstraint("tenant_id", "suite_id", "version", name="uk_suite_version_tenant_suite_version"),
    )


class Target(Base):
    __tablename__ = "target"

    id: Mapped[str] = mapped_column(String(26), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    adapter: Mapped[str] = mapped_column(String(64), nullable=False)
    adapter_version: Mapped[str] = mapped_column(String(32), nullable=False, default="1")
    config_version: Mapped[str] = mapped_column(String(32), nullable=False, default="1")
    config: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False, default=utcnow_naive)
    created_by: Mapped[str] = mapped_column(String(64), nullable=False, default="system")

    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "name", "config_version", "adapter_version", name="uk_target_tenant_name_versions"
        ),
    )


class Run(Base):
    __tablename__ = "run"

    id: Mapped[str] = mapped_column(String(26), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(32), nullable=False)
    client_request_id: Mapped[str] = mapped_column(String(128), nullable=False)
    suite_id: Mapped[str | None] = mapped_column(String(26), nullable=True)
    suite_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    dataset_id: Mapped[str] = mapped_column(String(26), nullable=False, default="")
    dataset_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    dataset_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    manifest: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    manifest_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    mode: Mapped[str] = mapped_column(String(16), nullable=False, default="record")
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="queued")
    total_items: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    succeeded_items: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_items: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    skipped_items: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    budget_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False, default=utcnow_naive)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    created_by: Mapped[str] = mapped_column(String(64), nullable=False, default="system")

    __table_args__ = (
        UniqueConstraint("tenant_id", "client_request_id", name="uk_run_tenant_client_request"),
        Index("idx_run_tenant_status", "tenant_id", "status", "created_at"),
        Index("idx_run_tenant_manifest", "tenant_id", "manifest_hash"),
    )


class RunItem(Base):
    __tablename__ = "run_item"

    id: Mapped[str] = mapped_column(String(26), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(32), nullable=False)
    run_id: Mapped[str] = mapped_column(String(26), nullable=False)
    sample_key: Mapped[str] = mapped_column(String(128), nullable=False)
    sample_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    expected: Mapped[Any] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="pending")
    output: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    raw_ref: Mapped[str | None] = mapped_column(String(512), nullable=True)
    trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False, default=utcnow_naive)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), nullable=False, default=utcnow_naive, onupdate=utcnow_naive
    )

    __table_args__ = (
        UniqueConstraint("run_id", "sample_key", name="uk_run_item_run_sample"),
        Index("idx_run_item_tenant_run", "tenant_id", "run_id", "sample_index"),
        Index("idx_run_item_tenant_status", "tenant_id", "run_id", "status"),
    )


class Score(Base):
    __tablename__ = "score"

    id: Mapped[str] = mapped_column(String(26), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(32), nullable=False)
    run_id: Mapped[str] = mapped_column(String(26), nullable=False)
    run_item_id: Mapped[str] = mapped_column(String(26), nullable=False)
    metric_name: Mapped[str] = mapped_column(String(128), nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    passed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    evaluator_version_id: Mapped[str | None] = mapped_column(String(26), nullable=True)
    judge_call_id: Mapped[str | None] = mapped_column(String(26), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False, default=utcnow_naive)

    __table_args__ = (
        UniqueConstraint("run_item_id", "metric_name", name="uk_score_item_metric"),
        Index("idx_score_tenant_run_metric", "tenant_id", "run_id", "metric_name"),
    )


class JudgeCall(Base):
    __tablename__ = "judge_call"

    id: Mapped[str] = mapped_column(String(26), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(32), nullable=False)
    run_id: Mapped[str] = mapped_column(String(26), nullable=False)
    run_item_id: Mapped[str] = mapped_column(String(26), nullable=False)
    evaluator_version_id: Mapped[str | None] = mapped_column(String(26), nullable=True)
    model: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    prompt_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="succeeded")
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    request: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    response: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    parsed: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    raw_ref: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False, default=utcnow_naive)

    __table_args__ = (Index("idx_judge_call_tenant_run", "tenant_id", "run_id", "created_at"),)


class Baseline(Base):
    __tablename__ = "baseline"

    id: Mapped[str] = mapped_column(String(26), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(32), nullable=False)
    suite_id: Mapped[str] = mapped_column(String(26), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    run_id: Mapped[str] = mapped_column(String(26), nullable=False)
    manifest_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    frozen: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False, default=utcnow_naive)
    created_by: Mapped[str] = mapped_column(String(64), nullable=False, default="system")

    __table_args__ = (
        UniqueConstraint("tenant_id", "suite_id", "name", name="uk_baseline_tenant_suite_name"),
        Index("idx_baseline_tenant_suite", "tenant_id", "suite_id"),
    )
