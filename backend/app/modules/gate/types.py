"""Gate public DTOs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from app.modules.gate.rules import GateRule


@dataclass(frozen=True)
class GateResult:
    tenant_id: str
    suite_id: str
    run_id: str
    manifest_hash: str
    passed: bool
    status: Literal["passed", "failed", "insufficient_data"]
    rules: list[GateRule]
    evaluated_at: datetime
    gate_id: str = ""


@dataclass(frozen=True)
class GateView:
    id: str
    tenant_id: str
    suite_id: str
    name: str
    rules_version: int
    baseline_run_id: str | None
    enabled: bool
