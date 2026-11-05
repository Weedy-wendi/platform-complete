"""Evaluation DTOs and SPI types.

The public contract intentionally uses frozen dataclasses: callers receive
snapshots and cannot mutate a historical run.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal, Protocol

from app.core.context import TenantContext
from app.core.errors import AppError

RunMode = Literal["record", "replay"]
RunStatus = Literal["queued", "running", "paused_budget", "succeeded", "failed", "cancelled"]
ItemStatus = Literal["pending", "succeeded", "failed", "skipped"]
MetricDirection = Literal["higher_is_better", "lower_is_better"]


class BudgetExceededError(AppError):
    def __init__(self, message: str = "Evaluation budget exceeded", **details: Any) -> None:
        super().__init__("BUDGET_EXCEEDED", message, 409, False, details)


@dataclass(frozen=True)
class RunManifest:
    run_id: str
    dataset_hash: str
    evaluator_versions: list[dict[str, Any]]
    metric_configs: list[dict[str, Any]]
    target_config: dict[str, Any]
    sampling: dict[str, Any]
    code_version: str
    adapter_version: str
    target_config_version: str
    mode: RunMode
    env: str


@dataclass(frozen=True)
class SampleInput:
    sample_key: str
    payload: dict[str, Any] = field(default_factory=dict)
    expected: Any = None
    raw_ref: str | None = None
    trace_id: str | None = None


@dataclass(frozen=True)
class StartRunRequest:
    client_request_id: str
    dataset_id: str
    dataset_version: int
    dataset_hash: str
    samples: tuple[SampleInput, ...]
    target_config: dict[str, Any]
    evaluator_versions: tuple[dict[str, Any], ...] = ()
    metric_configs: tuple[dict[str, Any], ...] = ()
    sampling: dict[str, Any] = field(default_factory=lambda: {"strategy": "full", "seed": 0})
    code_version: str = "dev"
    adapter_version: str = "1"
    target_config_version: str = "1"
    mode: RunMode = "record"
    env: str = "local"
    suite_id: str | None = None
    suite_version: int | None = None
    budget_usd: float | None = None
    estimated_cost_usd: float = 0.0


@dataclass(frozen=True)
class MetricSummary:
    name: str
    value: float
    count: int = 0
    stdev: float = 0.0
    direction: MetricDirection = "higher_is_better"


@dataclass(frozen=True)
class ScoreView:
    metric_name: str
    value: float
    passed: bool | None = None
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RunItemView:
    id: str
    run_id: str
    sample_key: str
    status: str
    sample_index: int = 0
    output: str | None = None
    error: str | None = None
    latency_ms: int = 0
    cost_usd: float = 0.0
    raw_ref: str | None = None
    trace_id: str | None = None
    scores: list[ScoreView] = field(default_factory=list)


@dataclass(frozen=True)
class RunView:
    run_id: str
    tenant_id: str
    status: str
    mode: str
    manifest_hash: str
    dataset_id: str
    dataset_version: int
    suite_id: str | None
    suite_version: int | None
    total_items: int
    succeeded_items: int
    failed_items: int
    skipped_items: int
    cost_usd: float
    budget_usd: float | None
    progress: int
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    error: str | None
    metrics: list[MetricSummary] = field(default_factory=list)

    def metric(self, name: str) -> MetricSummary | None:
        for summary in self.metrics:
            if summary.name == name:
                return summary
        return None


@dataclass(frozen=True)
class RunItemQuery:
    status: str | None = None
    metric: str | None = None
    cursor: str | None = None
    limit: int = 20


@dataclass(frozen=True)
class RunQuery:
    status: str | None = None
    suite_id: str | None = None
    cursor: str | None = None
    limit: int = 20


@dataclass(frozen=True)
class MetricComparison:
    name: str
    baseline: float
    candidate: float
    delta: float
    delta_pct: float
    direction: MetricDirection
    significant: bool
    ci_low: float | None = None
    ci_high: float | None = None
    baseline_n: int = 0
    candidate_n: int = 0


@dataclass(frozen=True)
class ComparisonView:
    run_a: str
    run_b: str
    metrics: list[MetricComparison]
    regressions: list[MetricComparison]
    improvements: list[MetricComparison]
    warnings: list[str]
    comparable: bool = True


@dataclass(frozen=True)
class AgentRequest:
    sample_key: str
    payload: dict[str, Any]
    expected: Any = None
    trace_id: str | None = None
    raw_ref: str | None = None
    model: str | None = None
    temperature: float = 0.0
    seed: int | None = None
    timeout_seconds: float = 30.0


@dataclass(frozen=True)
class AgentResponse:
    output: str
    trace_id: str | None = None
    usage: dict[str, int] = field(default_factory=dict)
    cost_usd: float = 0.0
    raw_ref: str | None = None
    finish_reason: str | None = None
    raw: Any = None


@dataclass(frozen=True)
class TraceSpan:
    trace_id: str
    span_id: str
    name: str
    parent_span_id: str | None = None
    kind: str = "internal"
    start_time_ns: int = 0
    end_time_ns: int = 0
    attributes: dict[str, Any] = field(default_factory=dict)
    status: str = "unset"
    tenant_id: str = ""


@dataclass(frozen=True)
class NormalizedTrace:
    trace_id: str
    spans: list[TraceSpan]
    issues: list[str] = field(default_factory=list)
    degraded: bool = False


class TargetAdapter(Protocol):
    def invoke(self, ctx: TenantContext, request: AgentRequest) -> AgentResponse: ...


class TraceSource(Protocol):
    def fetch(self, ctx: TenantContext, trace_id: str) -> list[TraceSpan]: ...


@dataclass(frozen=True)
class EvaluatorView:
    id: str
    tenant_id: str
    name: str
    kind: str
    latest_version: int


@dataclass(frozen=True)
class EvaluatorVersionView:
    id: str
    evaluator_id: str
    version: int
    config: dict[str, Any]
    config_hash: str


@dataclass(frozen=True)
class MetricView:
    id: str
    tenant_id: str
    name: str
    direction: str


@dataclass(frozen=True)
class SuiteView:
    id: str
    tenant_id: str
    name: str
    latest_version: int


@dataclass(frozen=True)
class SuiteVersionView:
    id: str
    suite_id: str
    version: int
    evaluator_versions: list[dict[str, Any]]
    metric_configs: list[dict[str, Any]]


@dataclass(frozen=True)
class TargetView:
    id: str
    tenant_id: str
    name: str
    adapter: str
    adapter_version: str
    config_version: str
    config: dict[str, Any]


@dataclass(frozen=True)
class BaselineView:
    id: str
    tenant_id: str
    suite_id: str
    name: str
    run_id: str
    manifest_hash: str
    frozen: bool


@dataclass(frozen=True)
class ExecutionResult:
    run_id: str
    status: str
    processed: int
    succeeded: int
    failed: int
    skipped: int
    cost_usd: float
