"""Deterministic in-memory implementations of the REST ports.

These are only used when the platform has not injected a real adapter. They are
deliberately small: filter by tenant, enforce obvious invariants, and return
stable ordering so pagination can be exercised without MySQL.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, datetime
from html import escape as xml_escape
from typing import Any

from app.api.errors import conflict_error
from app.api.pagination import CursorCodec, page_records, query_fingerprint
from app.api.ports import (
    BadcaseHitRecord,
    BadcaseSearchRecord,
    ComparisonRecord,
    ConfigRecord,
    DatasetRecord,
    DatasetVersionRecord,
    DatasourceRecord,
    EvaluatorRecord,
    EvaluatorSpec,
    FunctionalRunRecord,
    GateRecord,
    IssuedKeyRecord,
    MetricDeltaRecord,
    MetricRecord,
    ProjectRecord,
    ProjectsPort,
    ProviderRecord,
    ReportRecord,
    RoleRecord,
    RunItemRecord,
    RunItemStatus,
    RunRecord,
    RunSpec,
    SampleRecord,
    ShareLinkRecord,
    TenantRecord,
    UserRecord,
)
from app.core.clock import utcnow
from app.core.context import TenantContext
from app.core.errors import InvalidArgumentError, NotFoundError
from app.core.ids import new_key_id, new_secret, new_ulid
from app.core.pagination import Page

_TERMINAL_RUN_STATUSES = frozenset({"succeeded", "succeeded_with_errors", "failed", "cancelled", "timed_out"})


def _stamp(value: datetime | None) -> str:
    return value.isoformat() if value else ""


def _record_key(updated_at: datetime | None, record_id: str) -> str:
    return f"{_stamp(updated_at)}|{record_id}"


class InMemoryProjects:
    def __init__(self, *, codec: CursorCodec | None = None) -> None:
        self._codec = codec or CursorCodec()
        self._projects: dict[str, tuple[str, ProjectRecord]] = {}
        self._idempotency: dict[tuple[str, str], str] = {}

    def list_projects(self, ctx: TenantContext, *, cursor: str | None, limit: int) -> Page[ProjectRecord]:
        rows = [record for tenant, record in self._projects.values() if tenant == ctx.tenant_id]
        return page_records(
            rows,
            limit=limit,
            cursor=cursor,
            codec=self._codec,
            tenant_id=ctx.tenant_id,
            route="projects",
            query_hash=query_fingerprint({}),
            key_fn=lambda item: _record_key(item.updated_at, item.id),
            reverse=True,
        )

    def create_project(
        self,
        ctx: TenantContext,
        *,
        name: str,
        description: str | None = None,
        idempotency_key: str | None = None,
    ) -> ProjectRecord:
        if idempotency_key:
            existing = self._idempotency.get((ctx.tenant_id, idempotency_key))
            if existing is not None:
                return self.get_project(ctx, existing)
        normalized = name.strip()
        for tenant, project in self._projects.values():
            if tenant == ctx.tenant_id and project.name == normalized:
                raise conflict_error("Project already exists", name=normalized)
        project = ProjectRecord(id=new_ulid(), name=normalized, description=description, updated_at=utcnow())
        self._projects[project.id] = (ctx.tenant_id, project)
        if idempotency_key:
            self._idempotency[(ctx.tenant_id, idempotency_key)] = project.id
        return project

    def get_project(self, ctx: TenantContext, project_id: str) -> ProjectRecord:
        stored = self._projects.get(project_id)
        if stored is None or stored[0] != ctx.tenant_id:
            raise NotFoundError("Project not found")
        return stored[1]

    def update_project(
        self,
        ctx: TenantContext,
        project_id: str,
        *,
        name: str | None = None,
        description: str | None = None,
    ) -> ProjectRecord:
        current = self.get_project(ctx, project_id)
        if name is not None:
            normalized = name.strip()
            for tenant, project in self._projects.values():
                if tenant == ctx.tenant_id and project.id != project_id and project.name == normalized:
                    raise conflict_error("Project already exists", name=normalized)
            current = replace(current, name=normalized)
        if description is not None:
            current = replace(current, description=description)
        current = replace(current, updated_at=utcnow())
        self._projects[project_id] = (ctx.tenant_id, current)
        return current

    def delete_project(self, ctx: TenantContext, project_id: str) -> None:
        self.get_project(ctx, project_id)
        del self._projects[project_id]


class InMemoryDatasets:
    def __init__(
        self,
        projects: ProjectsPort,
        *,
        codec: CursorCodec | None = None,
    ) -> None:
        self._projects = projects
        self._codec = codec or CursorCodec()
        self._datasets: dict[str, tuple[str, DatasetRecord]] = {}
        self._versions: dict[tuple[str, str, int], DatasetVersionRecord] = {}
        self._samples: dict[tuple[str, str, int], list[SampleRecord]] = {}
        self._idempotency: dict[tuple[str, str], str] = {}

    def search_datasets(
        self,
        ctx: TenantContext,
        *,
        query: str | None = None,
        project_id: str | None = None,
        tags: tuple[str, ...] = (),
        cursor: str | None = None,
        limit: int = 20,
    ) -> Page[DatasetRecord]:
        needle = query.strip().lower() if query else None
        wanted = set(tags)
        rows = []
        for tenant, dataset in self._datasets.values():
            if tenant != ctx.tenant_id:
                continue
            if project_id is not None and dataset.project_id != project_id:
                continue
            if needle and needle not in dataset.name.lower():
                continue
            if wanted and not wanted.issubset(set(dataset.tags)):
                continue
            rows.append(dataset)
        return page_records(
            rows,
            limit=limit,
            cursor=cursor,
            codec=self._codec,
            tenant_id=ctx.tenant_id,
            route="datasets",
            query_hash=query_fingerprint({"query": query, "project_id": project_id, "tags": sorted(tags)}),
            key_fn=lambda item: _record_key(item.updated_at, item.id),
            reverse=True,
        )

    def create_dataset(
        self,
        ctx: TenantContext,
        *,
        project_id: str,
        name: str,
        tags: tuple[str, ...] = (),
        idempotency_key: str | None = None,
    ) -> DatasetRecord:
        if idempotency_key:
            existing = self._idempotency.get((ctx.tenant_id, idempotency_key))
            if existing is not None:
                return self._get_dataset(ctx, existing)
        self._projects.get_project(ctx, project_id)
        normalized = name.strip()
        for tenant, dataset in self._datasets.values():
            if tenant == ctx.tenant_id and dataset.project_id == project_id and dataset.name == normalized:
                raise conflict_error("Dataset already exists", name=normalized)
        dataset = DatasetRecord(
            id=new_ulid(),
            project_id=project_id,
            name=normalized,
            tags=tuple(tags),
            updated_at=utcnow(),
        )
        self._datasets[dataset.id] = (ctx.tenant_id, dataset)
        if idempotency_key:
            self._idempotency[(ctx.tenant_id, idempotency_key)] = dataset.id
        return dataset

    def _get_dataset(self, ctx: TenantContext, dataset_id: str) -> DatasetRecord:
        stored = self._datasets.get(dataset_id)
        if stored is None or stored[0] != ctx.tenant_id:
            raise NotFoundError("Dataset not found")
        return stored[1]

    def publish_version(
        self,
        ctx: TenantContext,
        dataset_id: str,
        *,
        schema: dict[str, Any],
        content_hash: str,
        samples: tuple[dict[str, Any], ...] = (),
        idempotency_key: str | None = None,
    ) -> DatasetVersionRecord:
        dataset = self._get_dataset(ctx, dataset_id)
        for (tenant, ds_id, _version), candidate in self._versions.items():
            if tenant == ctx.tenant_id and ds_id == dataset_id and candidate.content_hash == content_hash:
                return candidate

        version_number = (
            max(
                (
                    version
                    for tenant, ds_id, version in self._versions
                    if tenant == ctx.tenant_id and ds_id == dataset_id
                ),
                default=0,
            )
            + 1
        )
        normalized_samples: list[SampleRecord] = []
        for sample in samples:
            sample_key = str(sample.get("sample_key") or sample.get("id") or "").strip()
            if not sample_key:
                raise conflict_error("sample_key is required")
            normalized_samples.append(
                SampleRecord(
                    sample_id=sample_key,
                    payload=dict(sample.get("payload") or sample),
                    tags=tuple(sample.get("tags") or ()),
                )
            )

        version = DatasetVersionRecord(
            dataset_id=dataset_id,
            version=version_number,
            content_hash=content_hash,
            row_count=len(normalized_samples),
            schema=dict(schema),
        )
        self._versions[(ctx.tenant_id, dataset_id, version_number)] = version
        self._samples[(ctx.tenant_id, dataset_id, version_number)] = normalized_samples
        self._datasets[dataset_id] = (
            ctx.tenant_id,
            replace(
                dataset,
                latest_version=version_number,
                sample_count=len(normalized_samples),
                updated_at=utcnow(),
            ),
        )
        if idempotency_key:
            self._idempotency[(ctx.tenant_id, idempotency_key)] = f"{dataset_id}:{version_number}"
        return version

    def page_samples(
        self,
        ctx: TenantContext,
        dataset_id: str,
        version: int,
        *,
        cursor: str | None = None,
        limit: int = 20,
    ) -> Page[SampleRecord]:
        self._get_dataset(ctx, dataset_id)
        if (ctx.tenant_id, dataset_id, version) not in self._versions:
            raise NotFoundError("Dataset version not found")
        rows = self._samples.get((ctx.tenant_id, dataset_id, version), [])
        return page_records(
            rows,
            limit=limit,
            cursor=cursor,
            codec=self._codec,
            tenant_id=ctx.tenant_id,
            route="dataset_samples",
            query_hash=query_fingerprint({"dataset_id": dataset_id, "version": version}),
            key_fn=lambda item: item.sample_id,
        )


class InMemoryDatasources:
    def __init__(self, *, codec: CursorCodec | None = None) -> None:
        self._codec = codec or CursorCodec()
        self._datasources: dict[str, tuple[str, DatasourceRecord]] = {}
        self._idempotency: dict[tuple[str, str], str] = {}

    def list_datasources(
        self,
        ctx: TenantContext,
        *,
        cursor: str | None,
        limit: int,
    ) -> Page[DatasourceRecord]:
        rows = [record for tenant, record in self._datasources.values() if tenant == ctx.tenant_id]
        return page_records(
            rows,
            limit=limit,
            cursor=cursor,
            codec=self._codec,
            tenant_id=ctx.tenant_id,
            route="datasources",
            query_hash=query_fingerprint({}),
            key_fn=lambda item: _record_key(item.updated_at, item.id),
            reverse=True,
        )

    def create_datasource(
        self,
        ctx: TenantContext,
        *,
        name: str,
        description: str | None = None,
        kind: str = "generic",
        config: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> DatasourceRecord:
        if idempotency_key:
            existing = self._idempotency.get((ctx.tenant_id, idempotency_key))
            if existing is not None:
                return self.get_datasource(ctx, existing)
        normalized = name.strip()
        for tenant, datasource in self._datasources.values():
            if tenant == ctx.tenant_id and datasource.name == normalized:
                raise conflict_error("Datasource already exists", name=normalized)
        datasource = DatasourceRecord(
            id=new_ulid(),
            name=normalized,
            description=description,
            kind=kind,
            config=dict(config or {}),
            updated_at=utcnow(),
        )
        self._datasources[datasource.id] = (ctx.tenant_id, datasource)
        if idempotency_key:
            self._idempotency[(ctx.tenant_id, idempotency_key)] = datasource.id
        return datasource

    def get_datasource(self, ctx: TenantContext, datasource_id: str) -> DatasourceRecord:
        stored = self._datasources.get(datasource_id)
        if stored is None or stored[0] != ctx.tenant_id:
            raise NotFoundError("Datasource not found")
        return stored[1]

    def update_datasource(
        self,
        ctx: TenantContext,
        datasource_id: str,
        *,
        name: str | None = None,
        description: str | None = None,
        kind: str | None = None,
        config: dict[str, Any] | None = None,
    ) -> DatasourceRecord:
        current = self.get_datasource(ctx, datasource_id)
        if name is not None:
            normalized = name.strip()
            for tenant, datasource in self._datasources.values():
                if tenant == ctx.tenant_id and datasource.id != datasource_id and datasource.name == normalized:
                    raise conflict_error("Datasource already exists", name=normalized)
            current = replace(current, name=normalized)
        if description is not None:
            current = replace(current, description=description)
        if kind is not None:
            current = replace(current, kind=kind)
        if config is not None:
            current = replace(current, config=dict(config))
        current = replace(current, version=current.version + 1, updated_at=utcnow())
        self._datasources[datasource_id] = (ctx.tenant_id, current)
        return current

    def delete_datasource(self, ctx: TenantContext, datasource_id: str) -> None:
        self.get_datasource(ctx, datasource_id)
        del self._datasources[datasource_id]


class _InMemoryConfigStore:
    """Shared tenant-scoped cursor pagination for suites and targets."""

    def __init__(self, route: str, *, codec: CursorCodec | None = None) -> None:
        self._route = route
        self._codec = codec or CursorCodec()
        self._records: dict[str, tuple[str, ConfigRecord]] = {}

    def list_records(
        self,
        ctx: TenantContext,
        *,
        cursor: str | None,
        limit: int,
    ) -> Page[ConfigRecord]:
        rows = [record for tenant, record in self._records.values() if tenant == ctx.tenant_id]
        return page_records(
            rows,
            limit=limit,
            cursor=cursor,
            codec=self._codec,
            tenant_id=ctx.tenant_id,
            route=self._route,
            query_hash=query_fingerprint({}),
            key_fn=lambda item: _record_key(item.updated_at, item.id),
            reverse=True,
        )

    def create_record(
        self,
        ctx: TenantContext,
        *,
        name: str,
        description: str | None = None,
        config: dict[str, Any] | None = None,
    ) -> ConfigRecord:
        record = ConfigRecord(
            id=new_ulid(),
            name=name.strip(),
            description=description,
            config=dict(config or {}),
            updated_at=utcnow(),
        )
        self._records[record.id] = (ctx.tenant_id, record)
        return record

    def get_record(self, ctx: TenantContext, record_id: str, label: str) -> ConfigRecord:
        stored = self._records.get(record_id)
        if stored is None or stored[0] != ctx.tenant_id:
            raise NotFoundError(f"{label} not found")
        return stored[1]


class InMemorySuites(_InMemoryConfigStore):
    def __init__(self, *, codec: CursorCodec | None = None) -> None:
        super().__init__("suites", codec=codec)

    def list_suites(self, ctx: TenantContext, *, cursor: str | None, limit: int) -> Page[ConfigRecord]:
        return self.list_records(ctx, cursor=cursor, limit=limit)

    def create_suite(
        self,
        ctx: TenantContext,
        *,
        name: str,
        description: str | None = None,
        config: dict[str, Any] | None = None,
    ) -> ConfigRecord:
        return self.create_record(ctx, name=name, description=description, config=config)

    def get_suite(self, ctx: TenantContext, suite_id: str) -> ConfigRecord:
        return self.get_record(ctx, suite_id, "Suite")


class InMemoryTargets(_InMemoryConfigStore):
    def __init__(self, *, codec: CursorCodec | None = None) -> None:
        super().__init__("targets", codec=codec)

    def list_targets(self, ctx: TenantContext, *, cursor: str | None, limit: int) -> Page[ConfigRecord]:
        return self.list_records(ctx, cursor=cursor, limit=limit)

    def create_target(
        self,
        ctx: TenantContext,
        *,
        name: str,
        description: str | None = None,
        config: dict[str, Any] | None = None,
    ) -> ConfigRecord:
        return self.create_record(ctx, name=name, description=description, config=config)

    def get_target(self, ctx: TenantContext, target_id: str) -> ConfigRecord:
        return self.get_record(ctx, target_id, "Target")


class InMemoryEvaluation:
    def __init__(
        self,
        *,
        codec: CursorCodec | None = None,
    ) -> None:
        self._codec = codec or CursorCodec()
        self._runs: dict[str, tuple[str, RunRecord]] = {}
        self._items: dict[str, list[tuple[str, RunItemRecord]]] = {}
        self._evaluators: dict[str, tuple[str, EvaluatorRecord]] = {}
        self._idempotency: dict[tuple[str, str], str] = {}

    def list_runs(
        self,
        ctx: TenantContext,
        *,
        suite_id: str | None = None,
        cursor: str | None = None,
        limit: int = 20,
    ) -> Page[RunRecord]:
        rows = [
            run
            for tenant, run in self._runs.values()
            if tenant == ctx.tenant_id and (suite_id is None or run.suite_id == suite_id)
        ]
        return page_records(
            rows,
            limit=limit,
            cursor=cursor,
            codec=self._codec,
            tenant_id=ctx.tenant_id,
            route="runs",
            query_hash=query_fingerprint({"suite_id": suite_id}),
            key_fn=lambda item: _record_key(item.started_at, item.run_id),
            reverse=True,
        )

    def create_run(
        self,
        ctx: TenantContext,
        spec: RunSpec,
        *,
        idempotency_key: str | None = None,
    ) -> RunRecord:
        if idempotency_key:
            existing = self._idempotency.get((ctx.tenant_id, idempotency_key))
            if existing is not None:
                return self.get_run(ctx, existing)
        manifest = json.dumps(
            {
                "suite_id": spec.suite_id,
                "suite_version": spec.suite_version,
                "dataset_id": spec.dataset_id,
                "dataset_version": spec.dataset_version,
                "target": spec.target_config,
            },
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
        run = RunRecord(
            run_id=new_ulid(),
            status="queued",
            progress=0.0,
            manifest_hash=hashlib.sha256(manifest.encode("utf-8")).hexdigest(),
            suite_id=spec.suite_id,
            suite_version=spec.suite_version,
            dataset_id=spec.dataset_id,
            dataset_version=spec.dataset_version,
            summary={"metrics": [], "item_counts": {"total": 0, "succeeded": 0, "failed": 0, "skipped": 0}},
            started_at=utcnow(),
        )
        self._runs[run.run_id] = (ctx.tenant_id, run)
        self._items[run.run_id] = []
        if idempotency_key:
            self._idempotency[(ctx.tenant_id, idempotency_key)] = run.run_id
        return run

    def get_run(self, ctx: TenantContext, run_id: str) -> RunRecord:
        stored = self._runs.get(run_id)
        if stored is None or stored[0] != ctx.tenant_id:
            raise NotFoundError("Run not found")
        return stored[1]

    def list_items(
        self,
        ctx: TenantContext,
        run_id: str,
        *,
        status: RunItemStatus | None = None,
        cursor: str | None = None,
        limit: int = 20,
    ) -> Page[RunItemRecord]:
        self.get_run(ctx, run_id)
        rows = [
            item
            for tenant, item in self._items.get(run_id, [])
            if tenant == ctx.tenant_id and (status is None or item.status == status)
        ]
        return page_records(
            rows,
            limit=limit,
            cursor=cursor,
            codec=self._codec,
            tenant_id=ctx.tenant_id,
            route="run_items",
            query_hash=query_fingerprint({"run_id": run_id, "status": status}),
            key_fn=lambda item: item.item_id,
        )

    def cancel_run(self, ctx: TenantContext, run_id: str) -> RunRecord:
        run = self.get_run(ctx, run_id)
        if run.status in _TERMINAL_RUN_STATUSES:
            raise conflict_error("Run is already terminal", run_id=run_id, status=run.status)
        cancelled = replace(run, status="cancelled", finished_at=utcnow())
        self._runs[run_id] = (ctx.tenant_id, cancelled)
        return cancelled

    def compare_runs(self, ctx: TenantContext, run_id: str, baseline_run_id: str) -> ComparisonRecord:
        candidate = self.get_run(ctx, run_id)
        baseline = self.get_run(ctx, baseline_run_id)
        warnings: list[str] = []
        if baseline.suite_id != candidate.suite_id:
            warnings.append("runs use different suites")
        if (baseline.dataset_id, baseline.dataset_version) != (candidate.dataset_id, candidate.dataset_version):
            warnings.append("runs use different dataset versions")

        baseline_metrics = {metric.name: metric for metric in baseline.metrics}
        candidate_metrics = {metric.name: metric for metric in candidate.metrics}
        deltas: list[MetricDeltaRecord] = []
        for name in sorted(set(baseline_metrics) & set(candidate_metrics)):
            left = baseline_metrics[name]
            right = candidate_metrics[name]
            delta = right.value - left.value
            delta_pct = (delta / abs(left.value) * 100.0) if left.value != 0 else 0.0
            deltas.append(
                MetricDeltaRecord(
                    name=name,
                    baseline=left.value,
                    candidate=right.value,
                    delta=delta,
                    delta_pct=delta_pct,
                    significant=abs(delta_pct) >= 5.0,
                )
            )
        regressions = tuple(
            item for item in deltas if item.delta != 0 and _is_regression(baseline_metrics[item.name], item.delta)
        )
        improvements = tuple(item for item in deltas if item.delta != 0 and item not in regressions)
        return ComparisonRecord(
            metrics=tuple(deltas),
            regressions=regressions,
            improvements=improvements,
            warnings=tuple(warnings),
        )

    def list_evaluators(self, ctx: TenantContext, *, project_id: str | None = None) -> list[EvaluatorRecord]:
        return [
            evaluator
            for tenant, evaluator in self._evaluators.values()
            if tenant == ctx.tenant_id
            and evaluator.published
            and (project_id is None or evaluator.project_id in {None, project_id})
        ]

    def create_evaluator(self, ctx: TenantContext, spec: EvaluatorSpec) -> EvaluatorRecord:
        evaluator = EvaluatorRecord(
            id=new_ulid(),
            name=spec.name,
            version=spec.version,
            kind=spec.kind,
            project_id=spec.project_id,
            description=spec.description,
            metrics=tuple(
                MetricRecord(
                    name=str(metric.get("name", "score")),
                    value=0.0,
                    direction=metric.get("direction", "higher_is_better"),
                )
                for metric in spec.metrics
            ),
            published=spec.published,
            config=dict(spec.config),
        )
        self._evaluators[evaluator.id] = (ctx.tenant_id, evaluator)
        return evaluator

    def get_evaluator(self, ctx: TenantContext, evaluator_id: str) -> EvaluatorRecord:
        stored = self._evaluators.get(evaluator_id)
        if stored is None or stored[0] != ctx.tenant_id:
            raise NotFoundError("Evaluator not found")
        return stored[1]


def _is_regression(metric: MetricRecord, delta: float) -> bool:
    if metric.direction == "lower_is_better":
        return delta > 0
    return delta < 0


class InMemoryGates:
    """Empty gate registry; tests or a real adapter supply results."""

    def __init__(self) -> None:
        self._results: dict[tuple[str, str, str], GateRecord] = {}

    def put(self, *, tenant_id: str, suite_id: str, run_id: str, gate: GateRecord) -> None:
        self._results[(tenant_id, suite_id, run_id)] = gate

    def read_gate(self, ctx: TenantContext, *, suite_id: str, run_id: str) -> GateRecord | None:
        return self._results.get((ctx.tenant_id, suite_id, run_id))


class InMemoryReports:
    def __init__(self, evaluation: Any) -> None:
        self._evaluation = evaluation

    def get_report(self, ctx: TenantContext, run_id: str, fmt: str) -> ReportRecord:
        run = self._evaluation.get_run(ctx, run_id)
        generated_at = utcnow().isoformat()
        if fmt == "markdown":
            metrics = "\n".join(f"- {metric.name}: {metric.value}" for metric in run.metrics) or "- none"
            content = (
                f"# Run {run.run_id}\n\n"
                f"- status: {run.status}\n"
                f"- manifest_hash: `{run.manifest_hash}`\n"
                f"- generated_at: {generated_at}\n\n"
                f"## Metrics\n\n{metrics}\n"
            )
            media_type = "text/markdown; charset=utf-8"
        elif fmt == "csv":
            lines = ["metric,value", *(f"{metric.name},{metric.value}" for metric in run.metrics)]
            content = "\n".join(lines) + "\n"
            media_type = "text/csv; charset=utf-8"
        elif fmt == "junit":
            failures = run.item_failed
            content = (
                '<?xml version="1.0" encoding="UTF-8"?>\n'
                f'<testsuite name="{xml_escape(run.run_id)}" tests="{run.item_total}" failures="{failures}">\n'
                "</testsuite>\n"
            )
            media_type = "application/xml; charset=utf-8"
        else:
            content = json.dumps(
                {
                    "run_id": run.run_id,
                    "status": run.status,
                    "manifest_hash": run.manifest_hash,
                    "summary": run.summary,
                    "metrics": [{"name": metric.name, "value": metric.value} for metric in run.metrics],
                    "generated_at": generated_at,
                },
                ensure_ascii=False,
            )
            media_type = "application/json"
        return ReportRecord(
            run_id=run.run_id,
            manifest_hash=run.manifest_hash,
            format=fmt,
            content=content,
            media_type=media_type,
        )

    def create_share_link(
        self,
        ctx: TenantContext,
        run_id: str,
        *,
        secret: str,
        ttl_seconds: int = 3600,
    ) -> ShareLinkRecord:
        if not secret:
            raise InvalidArgumentError("share link secret is required")
        if ttl_seconds <= 0:
            raise InvalidArgumentError("share link ttl must be positive")
        self._evaluation.get_run(ctx, run_id)
        expires_at = int(time.time()) + ttl_seconds
        payload = {
            "tenant_id": ctx.tenant_id,
            "run_id": run_id,
            "format": "json",
            "expires_at": expires_at,
        }
        encoded = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode("utf-8")).decode("ascii")
        signature = hmac.new(secret.encode("utf-8"), encoded.encode("ascii"), hashlib.sha256).hexdigest()[:32]
        return ShareLinkRecord(
            token=f"{encoded}.{signature}",
            expires_at=datetime.fromtimestamp(expires_at, tz=UTC),
        )

    def resolve_share_link(self, ctx: TenantContext, token: str, *, secret: str) -> ReportRecord:
        if not secret:
            raise InvalidArgumentError("share link secret is required")
        try:
            encoded, signature = token.split(".", 1)
        except ValueError as exc:
            raise InvalidArgumentError("invalid share link") from exc
        expected = hmac.new(secret.encode("utf-8"), encoded.encode("ascii"), hashlib.sha256).hexdigest()[:32]
        if not hmac.compare_digest(expected, signature):
            raise InvalidArgumentError("invalid share link signature")
        try:
            payload = json.loads(base64.urlsafe_b64decode(encoded.encode("ascii")))
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            raise InvalidArgumentError("invalid share link") from exc
        expires_at = int(payload.get("expires_at", 0))
        if expires_at < int(time.time()):
            raise InvalidArgumentError("share link has expired")
        if str(payload.get("tenant_id") or "") != ctx.tenant_id:
            raise NotFoundError("Report not found")
        run_id = str(payload.get("run_id") or "")
        if not run_id:
            raise InvalidArgumentError("invalid share link")
        return self.get_report(ctx, run_id, "json")


class InMemorySearch:
    """Deterministic local keyword search, always reported as degraded."""

    def __init__(self, hits: Sequence[BadcaseHitRecord] = (), *, degraded: bool = True) -> None:
        self._hits = list(hits)
        self._degraded = degraded

    def add(self, hit: BadcaseHitRecord) -> None:
        self._hits.append(hit)

    def search_badcases(
        self,
        ctx: TenantContext,
        *,
        query: str | None = None,
        dataset_id: str | None = None,
        tags: tuple[str, ...] = (),
        limit: int = 20,
    ) -> BadcaseSearchRecord:
        needle = query.strip().lower() if query else None
        wanted = set(tags)
        selected = []
        for hit in self._hits:
            if hit.tenant_id != ctx.tenant_id:
                continue
            if dataset_id is not None and hit.dataset_id != dataset_id:
                continue
            if wanted and not wanted.issubset(set(hit.tags)):
                continue
            if needle and needle not in hit.title.lower():
                continue
            selected.append(hit)
        selected.sort(key=lambda item: (-(item.similarity or 0.0), item.badcase_id))
        return BadcaseSearchRecord(items=tuple(selected[:limit]), degraded=self._degraded)


class InMemoryAdmin:
    def __init__(
        self,
        *,
        tenants: Sequence[TenantRecord] = (),
        providers: Sequence[ProviderRecord] = (),
        key_env: str = "dev",
    ) -> None:
        self._tenants = {tenant.id: tenant for tenant in tenants}
        self._users: dict[str, UserRecord] = {}
        self._roles: dict[str, tuple[str, RoleRecord]] = {}
        self._keys: dict[str, tuple[str, str, tuple[str, ...], datetime | None]] = {}
        self._providers = list(providers)
        self._key_env = key_env

    def list_tenants(self, ctx: TenantContext) -> list[TenantRecord]:
        return sorted(self._tenants.values(), key=lambda item: item.id)

    def create_tenant(self, ctx: TenantContext, *, name: str, slug: str) -> TenantRecord:
        if any(tenant.slug == slug for tenant in self._tenants.values()):
            raise conflict_error("Tenant slug already exists", slug=slug)
        tenant = TenantRecord(id=new_ulid(), name=name.strip(), slug=slug)
        self._tenants[tenant.id] = tenant
        return tenant

    def get_tenant(self, ctx: TenantContext, tenant_id: str) -> TenantRecord:
        tenant = self._tenants.get(tenant_id)
        if tenant is None:
            raise NotFoundError("Tenant not found")
        return tenant

    def set_tenant_status(self, ctx: TenantContext, tenant_id: str, status: str) -> TenantRecord:
        tenant = replace(self.get_tenant(ctx, tenant_id), status=status)
        self._tenants[tenant.id] = tenant
        return tenant

    def list_users(self, ctx: TenantContext) -> list[UserRecord]:
        return sorted(
            (user for user in self._users.values() if user.tenant_id == ctx.tenant_id),
            key=lambda item: item.id,
        )

    def create_user(self, ctx: TenantContext, *, email: str, roles: tuple[str, ...] = ()) -> UserRecord:
        normalized = email.strip().lower()
        if any(user.tenant_id == ctx.tenant_id and user.email == normalized for user in self._users.values()):
            raise conflict_error("User email already exists", email=normalized)
        user = UserRecord(
            id=new_ulid(),
            tenant_id=ctx.tenant_id,
            email=normalized,
            display_name=normalized.split("@")[0],
            roles=tuple(roles),
        )
        self._users[user.id] = user
        return user

    def get_user(self, ctx: TenantContext, user_id: str) -> UserRecord:
        user = self._users.get(user_id)
        if user is None or user.tenant_id != ctx.tenant_id:
            raise NotFoundError("User not found")
        return user

    def deactivate_user(self, ctx: TenantContext, user_id: str) -> None:
        user = self.get_user(ctx, user_id)
        self._users[user_id] = replace(user, status="disabled")

    def list_roles(self, ctx: TenantContext) -> list[RoleRecord]:
        return sorted(
            (role for tenant, role in self._roles.values() if tenant == ctx.tenant_id),
            key=lambda item: item.id,
        )

    def create_role(
        self,
        ctx: TenantContext,
        *,
        name: str,
        permissions: tuple[str, ...],
        description: str = "",
    ) -> RoleRecord:
        if any(tenant == ctx.tenant_id and role.name == name for tenant, role in self._roles.values()):
            raise conflict_error("Role already exists", name=name)
        role = RoleRecord(
            id=new_ulid(),
            name=name,
            description=description,
            permissions=tuple(sorted(set(permissions))),
        )
        self._roles[role.id] = (ctx.tenant_id, role)
        return role

    def issue_api_key(
        self,
        ctx: TenantContext,
        *,
        name: str,
        scopes: tuple[str, ...],
        expires_at: datetime | None = None,
    ) -> IssuedKeyRecord:
        key_id = new_key_id()
        record = IssuedKeyRecord(
            key_id=key_id,
            raw_key=f"pk_{self._key_env}_{key_id}_{new_secret()}",
            name=name,
            tenant_id=ctx.tenant_id,
            scopes=tuple(sorted(set(scopes))),
            expires_at=expires_at,
        )
        self._keys[key_id] = (ctx.tenant_id, name, record.scopes, expires_at)
        return record

    def revoke_api_key(self, ctx: TenantContext, key_id: str) -> None:
        stored = self._keys.get(key_id)
        if stored is None or stored[0] != ctx.tenant_id:
            raise NotFoundError("API key not found")
        del self._keys[key_id]

    def rotate_api_key(self, ctx: TenantContext, key_id: str) -> IssuedKeyRecord:
        stored = self._keys.get(key_id)
        if stored is None or stored[0] != ctx.tenant_id:
            raise NotFoundError("API key not found")
        tenant_id, name, scopes, expires_at = stored
        del self._keys[key_id]
        return self.issue_api_key(ctx, name=name, scopes=scopes, expires_at=expires_at)

    def list_providers(self, ctx: TenantContext) -> list[ProviderRecord]:
        return list(self._providers)


class InMemoryFunctional:
    def __init__(self, *, codec: CursorCodec | None = None) -> None:
        self._codec = codec or CursorCodec()
        self._runs: dict[str, tuple[str, FunctionalRunRecord]] = {}
        self._idempotency: dict[tuple[str, str], str] = {}

    def list_runs(
        self,
        ctx: TenantContext,
        *,
        cursor: str | None = None,
        limit: int = 20,
    ) -> Page[FunctionalRunRecord]:
        rows = [run for tenant, run in self._runs.values() if tenant == ctx.tenant_id]
        return page_records(
            rows,
            limit=limit,
            cursor=cursor,
            codec=self._codec,
            tenant_id=ctx.tenant_id,
            route="functional_runs",
            query_hash=query_fingerprint({}),
            key_fn=lambda item: item.run_id,
            reverse=True,
        )

    def create_run(
        self,
        ctx: TenantContext,
        *,
        suite_id: str,
        suite_version: str | None = None,
        idempotency_key: str | None = None,
    ) -> FunctionalRunRecord:
        if idempotency_key:
            existing = self._idempotency.get((ctx.tenant_id, idempotency_key))
            if existing is not None:
                return self.get_run(ctx, existing)
        run = FunctionalRunRecord(run_id=new_ulid(), status="queued", suite_id=suite_id)
        self._runs[run.run_id] = (ctx.tenant_id, run)
        if idempotency_key:
            self._idempotency[(ctx.tenant_id, idempotency_key)] = run.run_id
        return run

    def get_run(self, ctx: TenantContext, run_id: str) -> FunctionalRunRecord:
        stored = self._runs.get(run_id)
        if stored is None or stored[0] != ctx.tenant_id:
            raise NotFoundError("Functional run not found")
        return stored[1]


__all__ = [
    "InMemoryAdmin",
    "InMemoryDatasets",
    "InMemoryDatasources",
    "InMemoryEvaluation",
    "InMemoryFunctional",
    "InMemoryGates",
    "InMemoryProjects",
    "InMemoryReports",
    "InMemorySearch",
    "InMemorySuites",
    "InMemoryTargets",
]
