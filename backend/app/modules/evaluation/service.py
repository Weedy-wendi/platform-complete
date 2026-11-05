"""Evaluation use cases: immutable configuration, idempotent runs and comparison."""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.core.context import TenantContext
from app.core.errors import InvalidArgumentError, NotFoundError
from app.core.ids import new_ulid
from app.core.kill_switch import KILL_SWITCHES
from app.core.pagination import Page
from app.modules.evaluation.budget import validate_budget
from app.modules.evaluation.executor import RunExecutor
from app.modules.evaluation.judge import JudgeModelGateway
from app.modules.evaluation.manifest import (
    build_manifest,
    canonical_json,
    manifest_hash,
    manifest_to_dict,
    validate_start_request,
)
from app.modules.evaluation.models import (
    Baseline,
    EvalSuite,
    Evaluator,
    EvaluatorVersion,
    Metric,
    Run,
    RunItem,
    SuiteVersion,
    Target,
)
from app.modules.evaluation.reader import RunReader
from app.modules.evaluation.targets.config import validate_target_config
from app.modules.evaluation.types import (
    BaselineView,
    ComparisonView,
    EvaluatorVersionView,
    EvaluatorView,
    MetricView,
    RunItemQuery,
    RunItemView,
    RunQuery,
    RunView,
    StartRunRequest,
    SuiteVersionView,
    SuiteView,
    TargetAdapter,
    TargetView,
)
from app.modules.evaluation.views import run_view

_DECLARATIVE_ADAPTERS = {"http_json", "openai_compat"}


def _config_hash(config: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json(config).encode("utf-8")).hexdigest()


class EvaluationService:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        adapter: TargetAdapter | None = None,
        judge_gateway: JudgeModelGateway | None = None,
        max_workers: int = 1,
    ) -> None:
        self._session_factory = session_factory
        self._adapter = adapter
        self._judge_gateway = judge_gateway
        self._max_workers = max_workers
        self._reader = RunReader(session_factory)

    # Configuration ---------------------------------------------------------

    def create_evaluator(
        self,
        ctx: TenantContext,
        name: str,
        *,
        kind: str = "rule",
        description: str = "",
        config: dict[str, Any] | None = None,
    ) -> EvaluatorView:
        if not name.strip():
            raise InvalidArgumentError("evaluator name is required")
        if kind not in {"rule", "judge"}:
            raise InvalidArgumentError("evaluator kind must be rule or judge")
        with self._session_factory() as session:
            existing = session.scalar(
                select(Evaluator).where(Evaluator.tenant_id == ctx.tenant_id, Evaluator.name == name.strip())
            )
            if existing is not None:
                raise InvalidArgumentError("evaluator already exists", name=name)
            evaluator = Evaluator(
                id=new_ulid(),
                tenant_id=ctx.tenant_id,
                name=name.strip(),
                kind=kind,
                description=description,
                latest_version=1,
                created_by=ctx.subject_id,
            )
            session.add(evaluator)
            payload = dict(config or {"kind": kind})
            session.add(
                EvaluatorVersion(
                    id=new_ulid(),
                    tenant_id=ctx.tenant_id,
                    evaluator_id=evaluator.id,
                    version=1,
                    config=payload,
                    config_hash=_config_hash(payload),
                    created_by=ctx.subject_id,
                )
            )
            session.commit()
            return _evaluator_view(evaluator)

    def publish_evaluator_version(
        self,
        ctx: TenantContext,
        evaluator_id: str,
        config: dict[str, Any],
    ) -> EvaluatorVersionView:
        if not isinstance(config, dict) or not config:
            raise InvalidArgumentError("evaluator version config is required")
        with self._session_factory() as session:
            evaluator = self._get(session, ctx, Evaluator, evaluator_id, "Evaluator")
            version = (
                session.scalar(
                    select(func.max(EvaluatorVersion.version)).where(
                        EvaluatorVersion.tenant_id == ctx.tenant_id,
                        EvaluatorVersion.evaluator_id == evaluator_id,
                    )
                )
                or 0
            ) + 1
            row = EvaluatorVersion(
                id=new_ulid(),
                tenant_id=ctx.tenant_id,
                evaluator_id=evaluator_id,
                version=version,
                config=dict(config),
                config_hash=_config_hash(config),
                created_by=ctx.subject_id,
            )
            session.add(row)
            evaluator.latest_version = version
            session.commit()
            return _evaluator_version_view(row)

    def create_metric(
        self,
        ctx: TenantContext,
        name: str,
        *,
        direction: str = "higher_is_better",
        description: str = "",
        evaluator_id: str | None = None,
    ) -> MetricView:
        if not name.strip():
            raise InvalidArgumentError("metric name is required")
        if direction not in {"higher_is_better", "lower_is_better"}:
            raise InvalidArgumentError("metric direction is invalid", direction=direction)
        with self._session_factory() as session:
            existing = session.scalar(
                select(Metric).where(Metric.tenant_id == ctx.tenant_id, Metric.name == name.strip())
            )
            if existing is not None:
                raise InvalidArgumentError("metric already exists", name=name)
            row = Metric(
                id=new_ulid(),
                tenant_id=ctx.tenant_id,
                name=name.strip(),
                direction=direction,
                description=description,
                evaluator_id=evaluator_id,
            )
            session.add(row)
            session.commit()
            return _metric_view(row)

    def create_suite(self, ctx: TenantContext, name: str, *, description: str = "") -> SuiteView:
        if not name.strip():
            raise InvalidArgumentError("suite name is required")
        with self._session_factory() as session:
            existing = session.scalar(
                select(EvalSuite).where(EvalSuite.tenant_id == ctx.tenant_id, EvalSuite.name == name.strip())
            )
            if existing is not None:
                raise InvalidArgumentError("suite already exists", name=name)
            suite = EvalSuite(
                id=new_ulid(),
                tenant_id=ctx.tenant_id,
                name=name.strip(),
                description=description,
                created_by=ctx.subject_id,
            )
            session.add(suite)
            session.commit()
            return _suite_view(suite)

    def publish_suite_version(
        self,
        ctx: TenantContext,
        suite_id: str,
        *,
        evaluator_versions: Sequence[dict[str, Any]],
        metric_configs: Sequence[dict[str, Any]],
    ) -> SuiteVersionView:
        if not evaluator_versions:
            raise InvalidArgumentError("suite version requires evaluator versions")
        with self._session_factory() as session:
            suite = self._get(session, ctx, EvalSuite, suite_id, "Suite")
            version = (
                session.scalar(
                    select(func.max(SuiteVersion.version)).where(
                        SuiteVersion.tenant_id == ctx.tenant_id,
                        SuiteVersion.suite_id == suite_id,
                    )
                )
                or 0
            ) + 1
            row = SuiteVersion(
                id=new_ulid(),
                tenant_id=ctx.tenant_id,
                suite_id=suite_id,
                version=version,
                evaluator_versions=[dict(item) for item in evaluator_versions],
                metric_configs=[dict(item) for item in metric_configs],
                created_by=ctx.subject_id,
            )
            session.add(row)
            suite.latest_version = version
            session.commit()
            return _suite_version_view(row)

    def create_target(
        self,
        ctx: TenantContext,
        name: str,
        config: dict[str, Any],
        *,
        adapter: str | None = None,
    ) -> TargetView:
        if not name.strip():
            raise InvalidArgumentError("target name is required")
        if not isinstance(config, dict) or not config:
            raise InvalidArgumentError("target config is required")
        selected = adapter or str(config.get("adapter") or "")
        if not selected:
            raise InvalidArgumentError("target adapter is required")
        adapter_version = str(config.get("adapter_version") or "1")
        config_version = str(config.get("config_version") or "1")
        if selected in _DECLARATIVE_ADAPTERS:
            validated = validate_target_config({**config, "adapter": selected})
            adapter_version = validated.adapter_version
            config_version = validated.config_version
        with self._session_factory() as session:
            existing = session.scalar(
                select(Target).where(
                    Target.tenant_id == ctx.tenant_id,
                    Target.name == name.strip(),
                    Target.adapter_version == adapter_version,
                    Target.config_version == config_version,
                )
            )
            if existing is not None:
                raise InvalidArgumentError("target version already exists", name=name)
            row = Target(
                id=new_ulid(),
                tenant_id=ctx.tenant_id,
                name=name.strip(),
                adapter=selected,
                adapter_version=adapter_version,
                config_version=config_version,
                config=dict(config),
                created_by=ctx.subject_id,
            )
            session.add(row)
            session.commit()
            return _target_view(row)

    def create_baseline(self, ctx: TenantContext, suite_id: str, name: str, run_id: str) -> BaselineView:
        if not name.strip():
            raise InvalidArgumentError("baseline name is required")
        with self._session_factory() as session:
            run = self._get(session, ctx, Run, run_id, "Run")
            if run.status not in {"succeeded", "failed"}:
                raise InvalidArgumentError("baseline requires a completed run", status=run.status)
            existing = session.scalar(
                select(Baseline).where(
                    Baseline.tenant_id == ctx.tenant_id,
                    Baseline.suite_id == suite_id,
                    Baseline.name == name.strip(),
                )
            )
            if existing is not None:
                if existing.run_id == run_id:
                    return _baseline_view(existing)
                raise InvalidArgumentError("baseline is frozen", name=name)
            row = Baseline(
                id=new_ulid(),
                tenant_id=ctx.tenant_id,
                suite_id=suite_id,
                name=name.strip(),
                run_id=run_id,
                manifest_hash=run.manifest_hash,
                frozen=True,
                created_by=ctx.subject_id,
            )
            session.add(row)
            session.commit()
            return _baseline_view(row)

    # Runs ------------------------------------------------------------------

    def start_run(self, ctx: TenantContext, request: StartRunRequest) -> RunView:
        KILL_SWITCHES.require("evaluation")
        validate_start_request(request)
        validate_budget(request.budget_usd, request.estimated_cost_usd)
        adapter_name = str(request.target_config.get("adapter") or "")
        if adapter_name in _DECLARATIVE_ADAPTERS:
            validate_target_config(request.target_config)
        with self._session_factory() as session:
            existing = session.scalar(
                select(Run).where(
                    Run.tenant_id == ctx.tenant_id,
                    Run.client_request_id == request.client_request_id,
                )
            )
            if existing is not None:
                return run_view(session, existing)

            run_id = new_ulid()
            manifest = build_manifest(run_id, request)
            run = Run(
                id=run_id,
                tenant_id=ctx.tenant_id,
                client_request_id=request.client_request_id,
                suite_id=request.suite_id,
                suite_version=request.suite_version,
                dataset_id=request.dataset_id,
                dataset_version=request.dataset_version,
                dataset_hash=request.dataset_hash,
                manifest=manifest_to_dict(manifest),
                manifest_hash=manifest_hash(manifest),
                mode=request.mode,
                status="queued",
                total_items=len(request.samples),
                budget_usd=request.budget_usd,
                created_by=ctx.subject_id,
            )
            session.add(run)
            for index, sample in enumerate(request.samples):
                session.add(
                    RunItem(
                        id=new_ulid(),
                        tenant_id=ctx.tenant_id,
                        run_id=run_id,
                        sample_key=sample.sample_key,
                        sample_index=index,
                        payload=dict(sample.payload),
                        expected=sample.expected,
                        status="pending",
                        raw_ref=sample.raw_ref,
                        trace_id=sample.trace_id,
                    )
                )
            try:
                session.commit()
            except IntegrityError:
                session.rollback()
                existing = session.scalar(
                    select(Run).where(
                        Run.tenant_id == ctx.tenant_id,
                        Run.client_request_id == request.client_request_id,
                    )
                )
                if existing is None:
                    raise
                return run_view(session, existing)
            return run_view(session, run)

    def execute(
        self,
        ctx: TenantContext,
        run_id: str,
        *,
        adapter: TargetAdapter | None = None,
        judge_gateway: JudgeModelGateway | None = None,
        artifact_store: Any = None,
        max_workers: int | None = None,
    ) -> RunView:
        KILL_SWITCHES.require("evaluation")
        executor = RunExecutor(
            self._session_factory,
            adapter=adapter or self._adapter,
            judge_gateway=judge_gateway or self._judge_gateway,
            artifact_store=artifact_store,
            max_workers=max_workers or self._max_workers,
        )
        return executor.execute(ctx, run_id)

    def cancel(self, ctx: TenantContext, run_id: str) -> RunView:
        return RunExecutor(self._session_factory).cancel(ctx, run_id)

    def get_run(self, ctx: TenantContext, run_id: str) -> RunView:
        return self._reader.get_run(ctx, run_id)

    def list_runs(self, ctx: TenantContext, query: RunQuery | None = None) -> Page[RunView]:
        return self._reader.list_runs(ctx, query)

    def list_items(
        self,
        ctx: TenantContext,
        run_id: str,
        query: RunItemQuery | None = None,
    ) -> Page[RunItemView]:
        return self._reader.list_items(ctx, run_id, query)

    def compare(
        self,
        ctx: TenantContext,
        run_a: str,
        run_b: str,
        metric_names: list[str] | None = None,
    ) -> ComparisonView:
        return self._reader.compare(ctx, run_a, run_b, metric_names)

    @staticmethod
    def _get(session: Session, ctx: TenantContext, model: type[Any], entity_id: str, label: str) -> Any:
        row = session.scalar(select(model).where(model.tenant_id == ctx.tenant_id, model.id == entity_id))
        if row is None:
            raise NotFoundError(f"{label} not found")
        return row


def _evaluator_view(row: Evaluator) -> EvaluatorView:
    return EvaluatorView(
        id=row.id,
        tenant_id=row.tenant_id,
        name=row.name,
        kind=row.kind,
        latest_version=row.latest_version,
    )


def _evaluator_version_view(row: EvaluatorVersion) -> EvaluatorVersionView:
    return EvaluatorVersionView(
        id=row.id,
        evaluator_id=row.evaluator_id,
        version=row.version,
        config=row.config,
        config_hash=row.config_hash,
    )


def _metric_view(row: Metric) -> MetricView:
    return MetricView(id=row.id, tenant_id=row.tenant_id, name=row.name, direction=row.direction)


def _suite_view(row: EvalSuite) -> SuiteView:
    return SuiteView(id=row.id, tenant_id=row.tenant_id, name=row.name, latest_version=row.latest_version)


def _suite_version_view(row: SuiteVersion) -> SuiteVersionView:
    return SuiteVersionView(
        id=row.id,
        suite_id=row.suite_id,
        version=row.version,
        evaluator_versions=row.evaluator_versions,
        metric_configs=row.metric_configs,
    )


def _target_view(row: Target) -> TargetView:
    return TargetView(
        id=row.id,
        tenant_id=row.tenant_id,
        name=row.name,
        adapter=row.adapter,
        adapter_version=row.adapter_version,
        config_version=row.config_version,
        config=row.config,
    )


def _baseline_view(row: Baseline) -> BaselineView:
    return BaselineView(
        id=row.id,
        tenant_id=row.tenant_id,
        suite_id=row.suite_id,
        name=row.name,
        run_id=row.run_id,
        manifest_hash=row.manifest_hash,
        frozen=row.frozen,
    )
