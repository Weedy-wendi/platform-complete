"""Pydantic request/response models for the REST contract."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.api.ports import (
    BadcaseHitRecord,
    BadcaseSearchRecord,
    ComparisonRecord,
    ConfigRecord,
    DatasetRecord,
    DatasetVersionRecord,
    DatasourceRecord,
    EvaluatorRecord,
    FunctionalRunRecord,
    GateRecord,
    IssuedKeyRecord,
    ProjectRecord,
    ProviderRecord,
    ReportRecord,
    RoleRecord,
    RunItemRecord,
    RunRecord,
    SampleRecord,
    ShareLinkRecord,
    TenantRecord,
    UserRecord,
)


class RequestModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ErrorBody(BaseModel):
    code: str
    message: str
    trace_id: str
    details: dict[str, Any] = Field(default_factory=dict)


# Shared pages --------------------------------------------------------------


class ProjectOut(BaseModel):
    id: str
    name: str
    description: str | None = None
    updated_at: datetime | None = None

    @classmethod
    def from_record(cls, record: ProjectRecord) -> ProjectOut:
        return cls(
            id=record.id,
            name=record.name,
            description=record.description,
            updated_at=record.updated_at,
        )


class ProjectPage(BaseModel):
    items: list[ProjectOut]
    next_cursor: str | None = None


class ProjectCreate(RequestModel):
    name: str = Field(min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=1024)


class ProjectUpdate(RequestModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=1024)


class DatasetOut(BaseModel):
    id: str
    project_id: str
    name: str
    latest_version: int
    sample_count: int
    tags: list[str] = Field(default_factory=list)
    updated_at: datetime | None = None

    @classmethod
    def from_record(cls, record: DatasetRecord) -> DatasetOut:
        return cls(
            id=record.id,
            project_id=record.project_id,
            name=record.name,
            latest_version=record.latest_version,
            sample_count=record.sample_count,
            tags=list(record.tags),
            updated_at=record.updated_at,
        )


class DatasetPage(BaseModel):
    items: list[DatasetOut]
    next_cursor: str | None = None


class DatasetCreate(RequestModel):
    project_id: str
    name: str = Field(min_length=1, max_length=128)
    tags: list[str] = Field(default_factory=list, max_length=20)


class SampleIn(RequestModel):
    sample_key: str = Field(min_length=1, max_length=256)
    payload: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)


class DatasetVersionCreate(RequestModel):
    schema_: dict[str, Any] = Field(alias="schema")
    content_hash: str = Field(min_length=1, max_length=128)
    samples: list[SampleIn] = Field(default_factory=list)


class DatasetVersionOut(BaseModel):
    dataset_id: str
    version: int
    content_hash: str
    row_count: int
    schema_: dict[str, Any] = Field(default_factory=dict, alias="schema")

    model_config = ConfigDict(populate_by_name=True)

    @classmethod
    def from_record(cls, record: DatasetVersionRecord) -> DatasetVersionOut:
        return cls(
            dataset_id=record.dataset_id,
            version=record.version,
            content_hash=record.content_hash,
            row_count=record.row_count,
            schema=record.schema,
        )


class SampleOut(BaseModel):
    sample_id: str
    payload: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)

    @classmethod
    def from_record(cls, record: SampleRecord) -> SampleOut:
        return cls(sample_id=record.sample_id, payload=record.payload, tags=list(record.tags))


class SamplePage(BaseModel):
    items: list[SampleOut]
    next_cursor: str | None = None


# Datasources / configuration -------------------------------------------------


class DatasourceOut(BaseModel):
    id: str
    name: str
    description: str | None = None
    kind: str = "generic"
    version: int = 1
    config: dict[str, Any] = Field(default_factory=dict)
    updated_at: datetime | None = None

    @classmethod
    def from_record(cls, record: DatasourceRecord) -> DatasourceOut:
        return cls(
            id=record.id,
            name=record.name,
            description=record.description,
            kind=record.kind,
            version=record.version,
            config=record.config,
            updated_at=record.updated_at,
        )


class DatasourcePage(BaseModel):
    items: list[DatasourceOut]
    next_cursor: str | None = None


class DatasourceCreate(RequestModel):
    name: str = Field(min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=1024)
    kind: str = Field(default="generic", min_length=1, max_length=64)
    config: dict[str, Any] = Field(default_factory=dict)


class DatasourceUpdate(RequestModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=1024)
    kind: str | None = Field(default=None, min_length=1, max_length=64)
    config: dict[str, Any] | None = None


class ConfigOut(BaseModel):
    id: str
    name: str
    description: str | None = None
    version: int = 1
    config: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_record(cls, record: ConfigRecord) -> ConfigOut:
        return cls(
            id=record.id,
            name=record.name,
            description=record.description,
            version=record.version,
            config=record.config,
        )


class ConfigPage(BaseModel):
    items: list[ConfigOut]
    next_cursor: str | None = None


class ConfigCreate(RequestModel):
    name: str = Field(min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=1024)
    config: dict[str, Any] = Field(default_factory=dict)


# Runs / evaluation ---------------------------------------------------------


class RunCreate(RequestModel):
    suite_id: str = Field(min_length=1, max_length=128)
    suite_version: str | None = Field(default=None, max_length=64)
    dataset_id: str = Field(min_length=1, max_length=128)
    dataset_version: int = Field(ge=1)
    target_config: dict[str, Any] = Field(default_factory=dict)
    baseline_run_id: str | None = None


class RunAccepted(BaseModel):
    run_id: str
    status: str
    manifest_hash: str | None = None


class RunOut(BaseModel):
    run_id: str
    status: str
    progress: float = Field(ge=0.0, le=1.0)
    manifest_hash: str
    summary: dict[str, Any] = Field(default_factory=dict)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error: dict[str, Any] | None = None

    @classmethod
    def from_record(cls, record: RunRecord) -> RunOut:
        return cls(
            run_id=record.run_id,
            status=record.status,
            progress=record.progress,
            manifest_hash=record.manifest_hash,
            summary=record.summary,
            started_at=record.started_at,
            finished_at=record.finished_at,
            error=record.error,
        )


class RunPage(BaseModel):
    items: list[RunOut]
    next_cursor: str | None = None


class RunCancelOut(BaseModel):
    run_id: str
    status: str


class RunItemOut(BaseModel):
    item_id: str
    sample_id: str
    status: str
    score: float | None = None
    latency_ms: int | None = None
    error: dict[str, Any] | None = None
    evidence_ref: str | None = None

    @classmethod
    def from_record(cls, record: RunItemRecord) -> RunItemOut:
        return cls(
            item_id=record.item_id,
            sample_id=record.sample_id,
            status=record.status,
            score=record.score,
            latency_ms=record.latency_ms,
            error=record.error,
            evidence_ref=record.evidence_ref,
        )


class RunItemPage(BaseModel):
    items: list[RunItemOut]
    next_cursor: str | None = None


class MetricDeltaOut(BaseModel):
    name: str
    baseline: float
    candidate: float
    delta: float
    delta_pct: float
    significant: bool


class CompareOut(BaseModel):
    metrics: list[MetricDeltaOut]
    warnings: list[str] = Field(default_factory=list)

    @classmethod
    def from_record(cls, record: ComparisonRecord) -> CompareOut:
        return cls(
            metrics=[
                MetricDeltaOut(
                    name=item.name,
                    baseline=item.baseline,
                    candidate=item.candidate,
                    delta=item.delta,
                    delta_pct=item.delta_pct,
                    significant=item.significant,
                )
                for item in record.metrics
            ],
            warnings=list(record.warnings),
        )


class EvaluatorMetricOut(BaseModel):
    name: str
    direction: str = "higher_is_better"


class EvaluatorOut(BaseModel):
    id: str
    name: str
    version: str
    kind: str
    project_id: str | None = None
    description: str | None = None
    metrics: list[EvaluatorMetricOut] = Field(default_factory=list)
    config: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_record(cls, record: EvaluatorRecord) -> EvaluatorOut:
        return cls(
            id=record.id,
            name=record.name,
            version=record.version,
            kind=record.kind,
            project_id=record.project_id,
            description=record.description,
            metrics=[EvaluatorMetricOut(name=metric.name, direction=metric.direction) for metric in record.metrics],
            config=record.config,
        )


class EvaluatorPage(BaseModel):
    items: list[EvaluatorOut]


class EvaluatorMetricIn(RequestModel):
    name: str = Field(min_length=1, max_length=128)
    direction: Literal["higher_is_better", "lower_is_better"] = "higher_is_better"


class EvaluatorCreate(RequestModel):
    name: str = Field(min_length=1, max_length=128)
    version: str | None = Field(default=None, min_length=1, max_length=64)
    kind: Literal["rule", "judge", "human"] = "rule"
    project_id: str | None = None
    description: str | None = Field(default=None, max_length=1024)
    metrics: list[EvaluatorMetricIn] = Field(default_factory=list)
    config: dict[str, Any] = Field(default_factory=dict)


# Gate / reports ------------------------------------------------------------


class GateRuleOut(BaseModel):
    name: str
    expected: str
    actual: str
    passed: bool
    evidence_ref: str | None = None


class GateOut(BaseModel):
    passed: bool
    manifest_hash: str | None = None
    evaluated_at: datetime | None = None
    rules: list[GateRuleOut] = Field(default_factory=list)

    @classmethod
    def from_record(cls, record: GateRecord) -> GateOut:
        return cls(
            passed=record.passed,
            manifest_hash=record.manifest_hash,
            evaluated_at=record.evaluated_at,
            rules=[
                GateRuleOut(
                    name=rule.name,
                    expected=rule.expected,
                    actual=rule.actual,
                    passed=rule.passed,
                    evidence_ref=rule.evidence_ref,
                )
                for rule in record.rules
            ],
        )


class ReportOut(BaseModel):
    run_id: str
    manifest_hash: str
    format: str
    generated: bool = True

    @classmethod
    def from_record(cls, record: ReportRecord) -> ReportOut:
        return cls(run_id=record.run_id, manifest_hash=record.manifest_hash, format=record.format)


class ShareLinkCreate(RequestModel):
    ttl_seconds: int = Field(default=3600, ge=1, le=604800)


class ShareLinkOut(BaseModel):
    token: str
    expires_at: datetime
    url: str

    @classmethod
    def from_record(cls, record: ShareLinkRecord) -> ShareLinkOut:
        return cls(
            token=record.token,
            expires_at=record.expires_at,
            url=f"/v1/share/{record.token}",
        )


# Search --------------------------------------------------------------------


class BadcaseSearchIn(RequestModel):
    query: str | None = Field(default=None, max_length=200)
    dataset_id: str | None = None
    tags: list[str] = Field(default_factory=list, max_length=10)
    limit: int = Field(default=20, ge=1, le=50)


class BadcaseHitOut(BaseModel):
    badcase_id: str
    title: str
    dataset_id: str | None = None
    sample_id: str | None = None
    tags: list[str] = Field(default_factory=list)
    similarity: float | None = None
    evidence_ref: str | None = None

    @classmethod
    def from_record(cls, record: BadcaseHitRecord) -> BadcaseHitOut:
        return cls(
            badcase_id=record.badcase_id,
            title=record.title,
            dataset_id=record.dataset_id,
            sample_id=record.sample_id,
            tags=list(record.tags),
            similarity=record.similarity,
            evidence_ref=record.evidence_ref,
        )


class BadcaseSearchOut(BaseModel):
    items: list[BadcaseHitOut]
    degraded: bool

    @classmethod
    def from_record(cls, record: BadcaseSearchRecord) -> BadcaseSearchOut:
        return cls(
            items=[BadcaseHitOut.from_record(item) for item in record.items],
            degraded=record.degraded,
        )


# Identity / admin ----------------------------------------------------------


class MeOut(BaseModel):
    tenant_id: str
    subject_id: str
    scopes: list[str]
    auth_method: str
    expires_at: datetime | None = None
    client_id: str | None = None
    api_key_id: int | None = None


class TenantOut(BaseModel):
    id: str
    name: str
    slug: str
    status: str

    @classmethod
    def from_record(cls, record: TenantRecord) -> TenantOut:
        return cls(id=record.id, name=record.name, slug=record.slug, status=record.status)


class TenantPage(BaseModel):
    items: list[TenantOut]


class TenantCreate(RequestModel):
    name: str = Field(min_length=1, max_length=128)
    slug: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$")


class TenantStatusIn(RequestModel):
    status: Literal["active", "disabled"]


class UserOut(BaseModel):
    id: str
    tenant_id: str
    email: str
    display_name: str
    status: str
    roles: list[str] = Field(default_factory=list)

    @classmethod
    def from_record(cls, record: UserRecord) -> UserOut:
        return cls(
            id=record.id,
            tenant_id=record.tenant_id,
            email=record.email,
            display_name=record.display_name,
            status=record.status,
            roles=list(record.roles),
        )


class UserPage(BaseModel):
    items: list[UserOut]


class UserCreate(RequestModel):
    email: str = Field(min_length=3, max_length=320)
    roles: list[str] = Field(default_factory=list, max_length=20)


class RoleOut(BaseModel):
    id: str
    name: str
    description: str = ""
    is_system: bool = False
    permissions: list[str] = Field(default_factory=list)

    @classmethod
    def from_record(cls, record: RoleRecord) -> RoleOut:
        return cls(
            id=record.id,
            name=record.name,
            description=record.description,
            is_system=record.is_system,
            permissions=list(record.permissions),
        )


class RolePage(BaseModel):
    items: list[RoleOut]


class RoleCreate(RequestModel):
    name: str = Field(min_length=1, max_length=128)
    description: str = Field(default="", max_length=1024)
    permissions: list[str] = Field(default_factory=list, max_length=100)


class IssuedKeyOut(BaseModel):
    key_id: str
    raw_key: str
    name: str
    tenant_id: str
    scopes: list[str] = Field(default_factory=list)
    expires_at: datetime | None = None

    @classmethod
    def from_record(cls, record: IssuedKeyRecord) -> IssuedKeyOut:
        return cls(
            key_id=record.key_id,
            raw_key=record.raw_key,
            name=record.name,
            tenant_id=record.tenant_id,
            scopes=list(record.scopes),
            expires_at=record.expires_at,
        )


class ApiKeyCreate(RequestModel):
    name: str = Field(min_length=1, max_length=128)
    scopes: list[str] = Field(default_factory=list, max_length=100)
    expires_at: datetime | None = None


class ProviderOut(BaseModel):
    name: str
    kind: str
    enabled: bool = True
    base_url: str | None = None

    @classmethod
    def from_record(cls, record: ProviderRecord) -> ProviderOut:
        return cls(name=record.name, kind=record.kind, enabled=record.enabled, base_url=record.base_url)


class ProviderPage(BaseModel):
    items: list[ProviderOut]


# Functional ----------------------------------------------------------------


class FunctionalRunCreate(RequestModel):
    suite_id: str = Field(min_length=1, max_length=128)
    suite_version: str | None = Field(default=None, max_length=64)


class FunctionalStepOut(BaseModel):
    step_id: str
    status: str
    evidence_ref: str | None = None
    visual_diff_ref: str | None = None


class FunctionalRunOut(BaseModel):
    run_id: str
    status: str
    suite_id: str | None = None
    steps: list[FunctionalStepOut] = Field(default_factory=list)

    @classmethod
    def from_record(cls, record: FunctionalRunRecord) -> FunctionalRunOut:
        return cls(
            run_id=record.run_id,
            status=record.status,
            suite_id=record.suite_id,
            steps=[
                FunctionalStepOut(
                    step_id=step.step_id,
                    status=step.status,
                    evidence_ref=step.evidence_ref,
                    visual_diff_ref=step.visual_diff_ref,
                )
                for step in record.steps
            ],
        )


class FunctionalRunPage(BaseModel):
    items: list[FunctionalRunOut]
    next_cursor: str | None = None


__all__ = [
    "ApiKeyCreate",
    "BadcaseHitOut",
    "BadcaseSearchIn",
    "BadcaseSearchOut",
    "CompareOut",
    "ConfigCreate",
    "ConfigOut",
    "ConfigPage",
    "DatasetCreate",
    "DatasetOut",
    "DatasetPage",
    "DatasetVersionCreate",
    "DatasetVersionOut",
    "DatasourceCreate",
    "DatasourceOut",
    "DatasourcePage",
    "DatasourceUpdate",
    "ErrorBody",
    "EvaluatorCreate",
    "EvaluatorMetricIn",
    "EvaluatorMetricOut",
    "EvaluatorOut",
    "EvaluatorPage",
    "FunctionalRunCreate",
    "FunctionalRunOut",
    "FunctionalRunPage",
    "FunctionalStepOut",
    "GateOut",
    "GateRuleOut",
    "IssuedKeyOut",
    "MeOut",
    "MetricDeltaOut",
    "ProjectCreate",
    "ProjectOut",
    "ProjectPage",
    "ProjectUpdate",
    "ProviderOut",
    "ProviderPage",
    "ReportOut",
    "RoleCreate",
    "RoleOut",
    "RolePage",
    "RunAccepted",
    "RunCancelOut",
    "RunCreate",
    "RunItemOut",
    "RunItemPage",
    "RunOut",
    "RunPage",
    "SampleIn",
    "SampleOut",
    "SamplePage",
    "ShareLinkCreate",
    "ShareLinkOut",
    "TenantCreate",
    "TenantOut",
    "TenantPage",
    "TenantStatusIn",
    "UserCreate",
    "UserOut",
    "UserPage",
]
