"""Ports used by the HTTP adapter.

The REST layer never imports another module's ORM models, repositories or
internal services. It talks to the immutable DTOs and protocols defined here;
the default in-memory implementations live in :mod:`app.api.memory` and a
production composition can inject adapters that delegate to ``module.public``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal, Protocol

from app.core.context import TenantContext
from app.core.pagination import Page

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


# Catalog -------------------------------------------------------------------


@dataclass(frozen=True)
class ProjectRecord:
    id: str
    name: str
    description: str | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True)
class DatasetRecord:
    id: str
    project_id: str
    name: str
    latest_version: int = 0
    sample_count: int = 0
    tags: tuple[str, ...] = ()
    updated_at: datetime | None = None


@dataclass(frozen=True)
class DatasetVersionRecord:
    dataset_id: str
    version: int
    content_hash: str
    row_count: int
    schema: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SampleRecord:
    sample_id: str
    payload: dict[str, Any] = field(default_factory=dict)
    tags: tuple[str, ...] = ()


@dataclass(frozen=True)
class DatasourceRecord:
    id: str
    name: str
    description: str | None = None
    kind: str = "generic"
    version: int = 1
    config: dict[str, Any] = field(default_factory=dict)
    updated_at: datetime | None = None


@dataclass(frozen=True)
class ConfigRecord:
    """Versioned suite/target configuration."""

    id: str
    name: str
    description: str | None = None
    version: int = 1
    config: dict[str, Any] = field(default_factory=dict)
    updated_at: datetime | None = None


# Evaluation ----------------------------------------------------------------


@dataclass(frozen=True)
class MetricRecord:
    name: str
    value: float
    direction: Literal["higher_is_better", "lower_is_better"] = "higher_is_better"


@dataclass(frozen=True)
class RunSpec:
    suite_id: str
    suite_version: str | None = None
    dataset_id: str | None = None
    dataset_version: int | None = None
    target_config: dict[str, Any] = field(default_factory=dict)
    baseline_run_id: str | None = None


@dataclass(frozen=True)
class RunRecord:
    run_id: str
    status: RunStatus
    progress: float
    manifest_hash: str
    suite_id: str | None = None
    suite_version: str | None = None
    dataset_id: str | None = None
    dataset_version: int | None = None
    summary: dict[str, Any] = field(default_factory=dict)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    metrics: tuple[MetricRecord, ...] = ()
    cost_usd: float = 0.0
    item_total: int = 0
    item_succeeded: int = 0
    item_failed: int = 0
    item_skipped: int = 0
    error: dict[str, Any] | None = None


@dataclass(frozen=True)
class RunItemRecord:
    item_id: str
    sample_id: str
    status: RunItemStatus
    score: float | None = None
    latency_ms: int | None = None
    error: dict[str, Any] | None = None
    evidence_ref: str | None = None


@dataclass(frozen=True)
class MetricDeltaRecord:
    name: str
    baseline: float
    candidate: float
    delta: float
    delta_pct: float
    significant: bool


@dataclass(frozen=True)
class ComparisonRecord:
    metrics: tuple[MetricDeltaRecord, ...] = ()
    regressions: tuple[MetricDeltaRecord, ...] = ()
    improvements: tuple[MetricDeltaRecord, ...] = ()
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class EvaluatorSpec:
    name: str
    version: str
    kind: EvaluatorKind = "rule"
    project_id: str | None = None
    description: str | None = None
    metrics: tuple[dict[str, Any], ...] = ()
    published: bool = True
    config: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EvaluatorRecord:
    id: str
    name: str
    version: str
    kind: EvaluatorKind
    project_id: str | None = None
    description: str | None = None
    metrics: tuple[MetricRecord, ...] = ()
    published: bool = True
    config: dict[str, Any] = field(default_factory=dict)


# Gate / reporting ----------------------------------------------------------


@dataclass(frozen=True)
class GateRuleRecord:
    name: str
    expected: str
    actual: str
    passed: bool
    evidence_ref: str | None = None


@dataclass(frozen=True)
class GateRecord:
    passed: bool
    rules: tuple[GateRuleRecord, ...] = ()
    manifest_hash: str | None = None
    evaluated_at: datetime | None = None


@dataclass(frozen=True)
class ReportRecord:
    run_id: str
    manifest_hash: str
    format: str
    content: str
    media_type: str


@dataclass(frozen=True)
class ShareLinkRecord:
    token: str
    expires_at: datetime


# Search --------------------------------------------------------------------


@dataclass(frozen=True)
class BadcaseHitRecord:
    badcase_id: str
    title: str
    tenant_id: str = ""
    dataset_id: str | None = None
    sample_id: str | None = None
    tags: tuple[str, ...] = ()
    similarity: float | None = None
    evidence_ref: str | None = None


@dataclass(frozen=True)
class BadcaseSearchRecord:
    items: tuple[BadcaseHitRecord, ...] = ()
    degraded: bool = False


# Admin ---------------------------------------------------------------------


@dataclass(frozen=True)
class TenantRecord:
    id: str
    name: str
    slug: str
    status: str = "active"


@dataclass(frozen=True)
class UserRecord:
    id: str
    tenant_id: str
    email: str
    display_name: str
    status: str = "active"
    roles: tuple[str, ...] = ()


@dataclass(frozen=True)
class RoleRecord:
    id: str
    name: str
    description: str = ""
    is_system: bool = False
    permissions: tuple[str, ...] = ()


@dataclass(frozen=True)
class IssuedKeyRecord:
    key_id: str
    raw_key: str
    name: str
    tenant_id: str
    scopes: tuple[str, ...] = ()
    expires_at: datetime | None = None


@dataclass(frozen=True)
class ProviderRecord:
    name: str
    kind: str
    enabled: bool = True
    base_url: str | None = None


# Functional ----------------------------------------------------------------


@dataclass(frozen=True)
class FunctionalStepRecord:
    step_id: str
    status: str
    evidence_ref: str | None = None
    visual_diff_ref: str | None = None


@dataclass(frozen=True)
class FunctionalRunRecord:
    run_id: str
    status: str
    suite_id: str | None = None
    steps: tuple[FunctionalStepRecord, ...] = ()


# Protocols -----------------------------------------------------------------


class ProjectsPort(Protocol):
    def list_projects(self, ctx: TenantContext, *, cursor: str | None, limit: int) -> Page[ProjectRecord]: ...

    def create_project(
        self,
        ctx: TenantContext,
        *,
        name: str,
        description: str | None = None,
        idempotency_key: str | None = None,
    ) -> ProjectRecord: ...

    def get_project(self, ctx: TenantContext, project_id: str) -> ProjectRecord: ...

    def update_project(
        self,
        ctx: TenantContext,
        project_id: str,
        *,
        name: str | None = None,
        description: str | None = None,
    ) -> ProjectRecord: ...

    def delete_project(self, ctx: TenantContext, project_id: str) -> None: ...


class DatasetsPort(Protocol):
    def search_datasets(
        self,
        ctx: TenantContext,
        *,
        query: str | None = None,
        project_id: str | None = None,
        tags: tuple[str, ...] = (),
        cursor: str | None = None,
        limit: int = 20,
    ) -> Page[DatasetRecord]: ...

    def create_dataset(
        self,
        ctx: TenantContext,
        *,
        project_id: str,
        name: str,
        tags: tuple[str, ...] = (),
        idempotency_key: str | None = None,
    ) -> DatasetRecord: ...

    def publish_version(
        self,
        ctx: TenantContext,
        dataset_id: str,
        *,
        schema: dict[str, Any],
        content_hash: str,
        samples: tuple[dict[str, Any], ...] = (),
        idempotency_key: str | None = None,
    ) -> DatasetVersionRecord: ...

    def page_samples(
        self,
        ctx: TenantContext,
        dataset_id: str,
        version: int,
        *,
        cursor: str | None = None,
        limit: int = 20,
    ) -> Page[SampleRecord]: ...


class DatasourcesPort(Protocol):
    def list_datasources(
        self,
        ctx: TenantContext,
        *,
        cursor: str | None,
        limit: int,
    ) -> Page[DatasourceRecord]: ...

    def create_datasource(
        self,
        ctx: TenantContext,
        *,
        name: str,
        description: str | None = None,
        kind: str = "generic",
        config: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> DatasourceRecord: ...

    def get_datasource(self, ctx: TenantContext, datasource_id: str) -> DatasourceRecord: ...

    def update_datasource(
        self,
        ctx: TenantContext,
        datasource_id: str,
        *,
        name: str | None = None,
        description: str | None = None,
        kind: str | None = None,
        config: dict[str, Any] | None = None,
    ) -> DatasourceRecord: ...

    def delete_datasource(self, ctx: TenantContext, datasource_id: str) -> None: ...


class EvaluationPort(Protocol):
    def list_runs(
        self,
        ctx: TenantContext,
        *,
        suite_id: str | None = None,
        cursor: str | None = None,
        limit: int = 20,
    ) -> Page[RunRecord]: ...

    def create_run(
        self,
        ctx: TenantContext,
        spec: RunSpec,
        *,
        idempotency_key: str | None = None,
    ) -> RunRecord: ...

    def get_run(self, ctx: TenantContext, run_id: str) -> RunRecord: ...

    def list_items(
        self,
        ctx: TenantContext,
        run_id: str,
        *,
        status: RunItemStatus | None = None,
        cursor: str | None = None,
        limit: int = 20,
    ) -> Page[RunItemRecord]: ...

    def cancel_run(self, ctx: TenantContext, run_id: str) -> RunRecord: ...

    def compare_runs(self, ctx: TenantContext, run_id: str, baseline_run_id: str) -> ComparisonRecord: ...

    def list_evaluators(self, ctx: TenantContext, *, project_id: str | None = None) -> list[EvaluatorRecord]: ...

    def create_evaluator(self, ctx: TenantContext, spec: EvaluatorSpec) -> EvaluatorRecord: ...

    def get_evaluator(self, ctx: TenantContext, evaluator_id: str) -> EvaluatorRecord: ...


class SuitesPort(Protocol):
    def list_suites(self, ctx: TenantContext, *, cursor: str | None, limit: int) -> Page[ConfigRecord]: ...

    def create_suite(
        self,
        ctx: TenantContext,
        *,
        name: str,
        description: str | None = None,
        config: dict[str, Any] | None = None,
    ) -> ConfigRecord: ...

    def get_suite(self, ctx: TenantContext, suite_id: str) -> ConfigRecord: ...


class TargetsPort(Protocol):
    def list_targets(self, ctx: TenantContext, *, cursor: str | None, limit: int) -> Page[ConfigRecord]: ...

    def create_target(
        self,
        ctx: TenantContext,
        *,
        name: str,
        description: str | None = None,
        config: dict[str, Any] | None = None,
    ) -> ConfigRecord: ...

    def get_target(self, ctx: TenantContext, target_id: str) -> ConfigRecord: ...


class GatePort(Protocol):
    def read_gate(self, ctx: TenantContext, *, suite_id: str, run_id: str) -> GateRecord | None: ...


class ReportsPort(Protocol):
    def get_report(self, ctx: TenantContext, run_id: str, fmt: str) -> ReportRecord: ...

    def create_share_link(
        self,
        ctx: TenantContext,
        run_id: str,
        *,
        secret: str,
        ttl_seconds: int = 3600,
    ) -> ShareLinkRecord: ...

    def resolve_share_link(self, ctx: TenantContext, token: str, *, secret: str) -> ReportRecord: ...


class SearchPort(Protocol):
    def search_badcases(
        self,
        ctx: TenantContext,
        *,
        query: str | None = None,
        dataset_id: str | None = None,
        tags: tuple[str, ...] = (),
        limit: int = 20,
    ) -> BadcaseSearchRecord: ...


class AdminPort(Protocol):
    def list_tenants(self, ctx: TenantContext) -> list[TenantRecord]: ...

    def create_tenant(self, ctx: TenantContext, *, name: str, slug: str) -> TenantRecord: ...

    def get_tenant(self, ctx: TenantContext, tenant_id: str) -> TenantRecord: ...

    def set_tenant_status(self, ctx: TenantContext, tenant_id: str, status: str) -> TenantRecord: ...

    def list_users(self, ctx: TenantContext) -> list[UserRecord]: ...

    def create_user(self, ctx: TenantContext, *, email: str, roles: tuple[str, ...] = ()) -> UserRecord: ...

    def get_user(self, ctx: TenantContext, user_id: str) -> UserRecord: ...

    def deactivate_user(self, ctx: TenantContext, user_id: str) -> None: ...

    def list_roles(self, ctx: TenantContext) -> list[RoleRecord]: ...

    def create_role(
        self,
        ctx: TenantContext,
        *,
        name: str,
        permissions: tuple[str, ...],
        description: str = "",
    ) -> RoleRecord: ...

    def issue_api_key(
        self,
        ctx: TenantContext,
        *,
        name: str,
        scopes: tuple[str, ...],
        expires_at: datetime | None = None,
    ) -> IssuedKeyRecord: ...

    def revoke_api_key(self, ctx: TenantContext, key_id: str) -> None: ...

    def rotate_api_key(self, ctx: TenantContext, key_id: str) -> IssuedKeyRecord: ...

    def list_providers(self, ctx: TenantContext) -> list[ProviderRecord]: ...


class FunctionalPort(Protocol):
    def list_runs(
        self,
        ctx: TenantContext,
        *,
        cursor: str | None = None,
        limit: int = 20,
    ) -> Page[FunctionalRunRecord]: ...

    def create_run(
        self,
        ctx: TenantContext,
        *,
        suite_id: str,
        suite_version: str | None = None,
        idempotency_key: str | None = None,
    ) -> FunctionalRunRecord: ...

    def get_run(self, ctx: TenantContext, run_id: str) -> FunctionalRunRecord: ...


__all__ = [
    "AdminPort",
    "BadcaseHitRecord",
    "BadcaseSearchRecord",
    "ComparisonRecord",
    "ConfigRecord",
    "DatasetRecord",
    "DatasetVersionRecord",
    "DatasetsPort",
    "DatasourceRecord",
    "DatasourcesPort",
    "EvaluatorKind",
    "EvaluatorRecord",
    "EvaluatorSpec",
    "EvaluationPort",
    "FunctionalPort",
    "FunctionalRunRecord",
    "FunctionalStepRecord",
    "GatePort",
    "GateRecord",
    "GateRuleRecord",
    "IssuedKeyRecord",
    "MetricDeltaRecord",
    "MetricRecord",
    "ProjectRecord",
    "ProjectsPort",
    "ProviderRecord",
    "ReportRecord",
    "ReportsPort",
    "RoleRecord",
    "RunItemRecord",
    "RunItemStatus",
    "RunRecord",
    "RunSpec",
    "RunStatus",
    "SampleRecord",
    "SearchPort",
    "ShareLinkRecord",
    "SuitesPort",
    "TargetsPort",
    "TenantRecord",
    "UserRecord",
]
