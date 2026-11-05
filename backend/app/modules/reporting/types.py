"""Reporting DTOs."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal


@dataclass(frozen=True)
class RunReport:
    run_id: str
    manifest_hash: str
    format: Literal["markdown", "json"]
    content: str
    generated_at: datetime


@dataclass(frozen=True)
class ComparisonReport:
    run_a: str
    run_b: str
    metrics: list[dict[str, Any]] = field(default_factory=list)
    regressions: list[dict[str, Any]] = field(default_factory=list)
    improvements: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ReadModelView:
    tenant_id: str
    run_id: str
    manifest_hash: str
    status: str
    metrics: list[dict[str, Any]]
    total_items: int
    succeeded_items: int
    failed_items: int
    skipped_items: int
    cost_usd: float
    updated_at: datetime


@dataclass(frozen=True)
class ShareTarget:
    tenant_id: str
    run_id: str
    format: str
    expires_at: int
