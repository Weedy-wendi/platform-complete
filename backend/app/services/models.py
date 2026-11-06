"""Read-only domain records exposed by the platform services.

These records mirror the platform's existing business entities. The MCP server
only ever reads them; no write path is defined here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

MetricDirection = Literal["higher_is_better", "lower_is_better"]
RunStatus = Literal[
    "queued",
    "dispatching",
    "running",
    "succeeded",
    "succeeded_with_errors",
    "failed",
    "cancelled",
    "timed_out",
]
RunItemStatus = Literal["succeeded", "failed", "skipped", "error"]
EvaluatorKind = Literal["rule", "judge", "human"]


@dataclass(frozen=True)
class Project:
    id: str
    tenant_id: str
    name: str
    description: str | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True)
class Dataset:
    id: str
    tenant_id: str
    project_id: str
    name: str
    latest_version: int
    sample_count: int
    tags: tuple[str, ...] = ()
    updated_at: datetime | None = None


@dataclass(frozen=True)
class SchemaField:
    name: str
    type: str
    nullable: bool = True
    description: str | None = None


@dataclass(frozen=True)
class DatasetVersion:
    dataset_id: str
    tenant_id: str
    version: int
    content_hash: str
    row_count: int
    fields: tuple[SchemaField, ...] = ()
    schema_json: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Sample:
    id: str
    tenant_id: str
    dataset_id: str
    version: int
    payload: dict[str, Any]
    tags: tuple[str, ...] = ()


@dataclass(frozen=True)
class MetricDefinition:
    name: str
    direction: MetricDirection = "higher_is_better"


@dataclass(frozen=True)
class Evaluator:
    id: str
    tenant_id: str
    name: str
    version: str
    kind: EvaluatorKind
    project_id: str | None = None
    description: str | None = None
    metrics: tuple[MetricDefinition, ...] = ()
    published: bool = True


@dataclass(frozen=True)
class MetricValue:
    name: str
    value: float
    direction: MetricDirection = "higher_is_better"


@dataclass(frozen=True)
class RunTarget:
    provider: str
    model: str


@dataclass(frozen=True)
class RunError:
    code: str
    message: str


@dataclass(frozen=True)
class Run:
    id: str
    tenant_id: str
    status: RunStatus
    progress: float
    manifest_hash: str
    suite_id: str | None = None
    suite_version: str | None = None
    dataset_id: str | None = None
    dataset_version: int | None = None
    target: RunTarget | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    metrics: tuple[MetricValue, ...] = ()
    cost_usd: float = 0.0
    item_total: int = 0
    item_succeeded: int = 0
    item_failed: int = 0
    item_skipped: int = 0
    error: RunError | None = None


@dataclass(frozen=True)
class RunItem:
    id: str
    tenant_id: str
    run_id: str
    sample_id: str
    status: RunItemStatus
    score: float | None = None
    latency_ms: int | None = None
    tokens: int | None = None
    error: RunError | None = None
    evidence_ref: str | None = None
    input: str | None = None
    output: str | None = None
    metrics: tuple[MetricValue, ...] = ()


@dataclass(frozen=True)
class Badcase:
    id: str
    tenant_id: str
    title: str
    dataset_id: str | None = None
    sample_id: str | None = None
    tags: tuple[str, ...] = ()
    created_at: datetime | None = None
    evidence_ref: str | None = None


@dataclass(frozen=True)
class BadcaseHit:
    badcase: Badcase
    similarity: float | None = None


@dataclass(frozen=True)
class BadcaseSearchResult:
    hits: list[BadcaseHit] = field(default_factory=list)
    degraded: bool = False


@dataclass(frozen=True)
class GateRuleResult:
    name: str
    expected: str
    actual: str
    passed: bool
    evidence_ref: str | None = None


@dataclass(frozen=True)
class GateResult:
    tenant_id: str
    suite_id: str
    run_id: str
    passed: bool
    rules: tuple[GateRuleResult, ...] = ()
    manifest_hash: str | None = None
    evaluated_at: datetime | None = None
