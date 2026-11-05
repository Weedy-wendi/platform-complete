"""Gate evaluation service. It only reads evaluation data and never mutates it."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.core.clock import utcnow_naive
from app.core.context import TenantContext
from app.core.errors import InvalidArgumentError, NotFoundError
from app.core.ids import new_ulid
from app.modules.evaluation.public import ComparisonView, RunReader, RunView
from app.modules.gate.metrics import GateMetrics
from app.modules.gate.models import Gate, GateResultRecord, GateRuleRecord
from app.modules.gate.rules import GateRule, RuleSpec, evaluate_rule, validate_rule
from app.modules.gate.types import GateResult, GateView


class EvaluationGateReader(Protocol):
    def get_run(self, ctx: TenantContext, run_id: str) -> RunView: ...
    def compare(
        self, ctx: TenantContext, run_a: str, run_b: str, metric_names: list[str] | None = None
    ) -> ComparisonView: ...


class GateReaderProtocol(Protocol):
    def read_gate(self, ctx: TenantContext, suite_id: str, run_id: str) -> GateResult | None: ...


class GateService:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        evaluation: EvaluationGateReader | None = None,
        metrics: GateMetrics | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._evaluation = evaluation or RunReader(session_factory)
        self.metrics = metrics or GateMetrics()

    def create_gate(
        self,
        ctx: TenantContext,
        suite_id: str,
        name: str,
        *,
        description: str = "",
        baseline_run_id: str | None = None,
    ) -> GateView:
        if not suite_id.strip():
            raise InvalidArgumentError("suite_id is required")
        if not name.strip():
            raise InvalidArgumentError("gate name is required")
        with self._session_factory() as session:
            existing = session.scalar(
                select(Gate).where(
                    Gate.tenant_id == ctx.tenant_id,
                    Gate.suite_id == suite_id,
                    Gate.name == name.strip(),
                )
            )
            if existing is not None:
                raise InvalidArgumentError("gate already exists", name=name)
            gate = Gate(
                id=new_ulid(),
                tenant_id=ctx.tenant_id,
                suite_id=suite_id,
                name=name.strip(),
                description=description,
                baseline_run_id=baseline_run_id,
                created_by=ctx.subject_id,
            )
            session.add(gate)
            session.commit()
            return _gate_view(gate)

    def add_rule(
        self,
        ctx: TenantContext,
        gate_id: str,
        *,
        name: str,
        kind: str,
        metric: str = "",
        operator: str = "gte",
        threshold: float = 0.0,
        baseline_run_id: str | None = None,
        min_samples: int | None = None,
    ) -> RuleSpec:
        spec = RuleSpec(
            name=name,
            kind=kind,
            metric=metric,
            operator=operator,
            threshold=float(threshold),
            baseline_run_id=baseline_run_id,
            min_samples=min_samples,
        )
        validate_rule(spec)
        with self._session_factory() as session:
            gate = self._get_gate(session, ctx, gate_id)
            duplicate = session.scalar(
                select(GateRuleRecord).where(
                    GateRuleRecord.tenant_id == ctx.tenant_id,
                    GateRuleRecord.gate_id == gate_id,
                    GateRuleRecord.name == name.strip(),
                )
            )
            if duplicate is not None:
                raise InvalidArgumentError("gate rule already exists", name=name)
            session.add(
                GateRuleRecord(
                    id=new_ulid(),
                    tenant_id=ctx.tenant_id,
                    gate_id=gate_id,
                    name=name.strip(),
                    kind=kind,
                    metric=metric.strip(),
                    operator=operator,
                    threshold=float(threshold),
                    baseline_run_id=baseline_run_id,
                    min_samples=min_samples,
                )
            )
            gate.rules_version += 1
            gate.updated_at = utcnow_naive()
            session.commit()
            return spec

    def list_rules(self, ctx: TenantContext, gate_id: str) -> list[RuleSpec]:
        with self._session_factory() as session:
            self._get_gate(session, ctx, gate_id)
            rows = session.scalars(
                select(GateRuleRecord)
                .where(GateRuleRecord.tenant_id == ctx.tenant_id, GateRuleRecord.gate_id == gate_id)
                .order_by(GateRuleRecord.created_at, GateRuleRecord.id)
            )
            return [_rule_spec(row) for row in rows]

    def get_gate(self, ctx: TenantContext, gate_id: str) -> GateView:
        with self._session_factory() as session:
            return _gate_view(self._get_gate(session, ctx, gate_id))

    def evaluate(
        self,
        ctx: TenantContext,
        run_id: str,
        gate_id: str,
        *,
        expected_manifest_hash: str | None = None,
    ) -> GateResult:
        with self._session_factory() as session:
            gate = self._get_gate(session, ctx, gate_id)
            rules = [
                _rule_spec(row)
                for row in session.scalars(
                    select(GateRuleRecord)
                    .where(GateRuleRecord.tenant_id == ctx.tenant_id, GateRuleRecord.gate_id == gate_id)
                    .order_by(GateRuleRecord.created_at, GateRuleRecord.id)
                )
            ]
        if not rules:
            raise InvalidArgumentError("gate has no rules", gate_id=gate_id)
        run = self._evaluation.get_run(ctx, run_id)
        if run.status not in {"succeeded", "failed"}:
            raise InvalidArgumentError("run is not complete", status=run.status)
        if not run.manifest_hash:
            raise InvalidArgumentError("run manifest is not reproducible")
        if expected_manifest_hash is not None and expected_manifest_hash != run.manifest_hash:
            raise InvalidArgumentError(
                "run manifest is not reproducible",
                expected_manifest_hash=expected_manifest_hash,
                actual_manifest_hash=run.manifest_hash,
            )

        baseline_ids = {
            baseline_id
            for baseline_id in [gate.baseline_run_id, *(rule.baseline_run_id for rule in rules)]
            if baseline_id
        }
        baseline_runs: dict[str, RunView] = {}
        comparisons: dict[str, ComparisonView] = {}
        for baseline_id in baseline_ids:
            baseline_runs[baseline_id] = self._evaluation.get_run(ctx, baseline_id)
            comparisons[baseline_id] = self._evaluation.compare(ctx, baseline_id, run_id)
        candidate_metrics = {summary.name: summary for summary in run.metrics}

        results: list[GateRule] = []
        insufficient = False
        hard_failed = False
        for spec in rules:
            selected_baseline_id = spec.baseline_run_id or gate.baseline_run_id
            baseline_summary = None
            comparison = None
            if selected_baseline_id is not None:
                baseline_run = baseline_runs.get(selected_baseline_id)
                if baseline_run is not None:
                    baseline_summary = {summary.name: summary for summary in baseline_run.metrics}.get(spec.metric)
                    comparison_view = comparisons.get(selected_baseline_id)
                    if comparison_view is not None:
                        comparison = next(
                            (item for item in comparison_view.metrics if item.name == spec.metric),
                            None,
                        )
            result, data_insufficient = evaluate_rule(
                spec,
                run_id=run_id,
                candidate=candidate_metrics.get(spec.metric),
                baseline=baseline_summary,
                comparison=comparison,
                baseline_run_id=selected_baseline_id,
                succeeded_items=run.succeeded_items,
            )
            results.append(result)
            insufficient = insufficient or data_insufficient
            hard_failed = hard_failed or (not result.passed and not data_insufficient)

        if hard_failed:
            status = "failed"
        elif insufficient:
            status = "insufficient_data"
        else:
            status = "passed"
        passed = status == "passed"
        evaluated_at = utcnow_naive()
        record = GateResultRecord(
            id=new_ulid(),
            tenant_id=ctx.tenant_id,
            gate_id=gate_id,
            suite_id=gate.suite_id,
            run_id=run_id,
            manifest_hash=run.manifest_hash,
            passed=passed,
            status=status,
            rules=[asdict(result) for result in results],
            evaluated_at=evaluated_at,
        )
        with self._session_factory() as session:
            session.add(record)
            session.commit()
        self.metrics.record(status)
        return GateResult(
            tenant_id=ctx.tenant_id,
            suite_id=gate.suite_id,
            run_id=run_id,
            manifest_hash=run.manifest_hash,
            passed=passed,
            status=status,  # type: ignore[arg-type]
            rules=results,
            evaluated_at=evaluated_at,
            gate_id=gate_id,
        )

    def read_gate(self, ctx: TenantContext, suite_id: str, run_id: str) -> GateResult | None:
        with self._session_factory() as session:
            row = session.scalar(
                select(GateResultRecord)
                .where(
                    GateResultRecord.tenant_id == ctx.tenant_id,
                    GateResultRecord.suite_id == suite_id,
                    GateResultRecord.run_id == run_id,
                )
                .order_by(GateResultRecord.evaluated_at.desc(), GateResultRecord.id.desc())
            )
            return _result_view(row) if row is not None else None

    def read_gate_for_gate(self, ctx: TenantContext, gate_id: str, run_id: str) -> GateResult | None:
        with self._session_factory() as session:
            row = session.scalar(
                select(GateResultRecord)
                .where(
                    GateResultRecord.tenant_id == ctx.tenant_id,
                    GateResultRecord.gate_id == gate_id,
                    GateResultRecord.run_id == run_id,
                )
                .order_by(GateResultRecord.evaluated_at.desc(), GateResultRecord.id.desc())
            )
            return _result_view(row) if row is not None else None

    def history(self, ctx: TenantContext, run_id: str) -> Sequence[GateResult]:
        with self._session_factory() as session:
            rows = session.scalars(
                select(GateResultRecord)
                .where(GateResultRecord.tenant_id == ctx.tenant_id, GateResultRecord.run_id == run_id)
                .order_by(GateResultRecord.evaluated_at, GateResultRecord.id)
            )
            return [_result_view(row) for row in rows]

    @staticmethod
    def _get_gate(session: Session, ctx: TenantContext, gate_id: str) -> Gate:
        gate = session.scalar(select(Gate).where(Gate.tenant_id == ctx.tenant_id, Gate.id == gate_id))
        if gate is None:
            raise NotFoundError("Gate not found")
        return gate


class GateReader:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        evaluation: EvaluationGateReader | None = None,
    ) -> None:
        self._service = GateService(session_factory, evaluation=evaluation)

    def read_gate(self, ctx: TenantContext, suite_id: str, run_id: str) -> GateResult | None:
        return self._service.read_gate(ctx, suite_id, run_id)

    def read_gate_for_gate(self, ctx: TenantContext, gate_id: str, run_id: str) -> GateResult | None:
        return self._service.read_gate_for_gate(ctx, gate_id, run_id)


def _rule_spec(row: GateRuleRecord) -> RuleSpec:
    return RuleSpec(
        name=row.name,
        kind=row.kind,
        metric=row.metric,
        operator=row.operator,
        threshold=row.threshold,
        baseline_run_id=row.baseline_run_id,
        min_samples=row.min_samples,
    )


def _gate_view(row: Gate) -> GateView:
    return GateView(
        id=row.id,
        tenant_id=row.tenant_id,
        suite_id=row.suite_id,
        name=row.name,
        rules_version=row.rules_version,
        baseline_run_id=row.baseline_run_id,
        enabled=row.enabled,
    )


def _result_view(row: GateResultRecord) -> GateResult:
    rules = [
        GateRule(
            name=str(item.get("name") or ""),
            kind=str(item.get("kind") or ""),
            expected=str(item.get("expected") or ""),
            actual=str(item.get("actual") or ""),
            passed=bool(item.get("passed")),
            evidence_ref=item.get("evidence_ref"),
        )
        for item in row.rules
        if isinstance(item, dict)
    ]
    return GateResult(
        tenant_id=row.tenant_id,
        suite_id=row.suite_id,
        run_id=row.run_id,
        manifest_hash=row.manifest_hash,
        passed=row.passed,
        status=row.status,  # type: ignore[arg-type]
        rules=rules,
        evaluated_at=row.evaluated_at,
        gate_id=row.gate_id,
    )
