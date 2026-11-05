"""In-process run executor with cancellation, progress and partial failures."""

from __future__ import annotations

import hashlib
import json
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.core.clock import utcnow_naive
from app.core.context import TenantContext
from app.core.errors import InvalidArgumentError, NotFoundError
from app.core.ids import new_ulid
from app.modules.evaluation.budget import is_over_budget
from app.modules.evaluation.judge import JudgeEvaluator, JudgeModelGateway, JudgeOutcome
from app.modules.evaluation.manifest import canonical_json
from app.modules.evaluation.models import JudgeCall, Run, RunItem, Score
from app.modules.evaluation.scoring import RuleScore, score_rule
from app.modules.evaluation.targets.replay import ReplayAdapter
from app.modules.evaluation.types import AgentRequest, AgentResponse, RunView, TargetAdapter
from app.modules.evaluation.views import run_view

_TERMINAL = {"succeeded", "failed", "cancelled"}


@dataclass(frozen=True)
class EvaluatorSpec:
    key: str
    kind: str
    metric: str
    direction: str
    rule: str = ""
    config: dict[str, Any] = field(default_factory=dict)
    version_id: str | None = None
    rubric: str = ""
    threshold: float = 0.7
    model: str | None = None


def parse_evaluator_specs(manifest: dict[str, Any]) -> list[EvaluatorSpec]:
    metric_configs = [item for item in manifest.get("metric_configs", []) or [] if isinstance(item, dict)]
    directions = {
        str(item.get("name") or item.get("metric")): str(item.get("direction") or "higher_is_better")
        for item in metric_configs
        if item.get("name") or item.get("metric")
    }
    fallback_metric = ""
    if len(metric_configs) == 1:
        fallback_metric = str(metric_configs[0].get("name") or metric_configs[0].get("metric") or "")
    specs: list[EvaluatorSpec] = []
    for index, entry in enumerate(manifest.get("evaluator_versions", []) or []):
        if not isinstance(entry, dict):
            continue
        metric_raw = entry.get("metric")
        if isinstance(metric_raw, dict):
            metric = str(metric_raw.get("name") or fallback_metric or "score")
            direction = str(metric_raw.get("direction") or directions.get(metric) or "higher_is_better")
        else:
            metric = str(metric_raw or fallback_metric or entry.get("metric_name") or entry.get("name") or "score")
            direction = str(entry.get("direction") or directions.get(metric) or "higher_is_better")
        rubric = str(entry.get("rubric") or "")
        kind = str(entry.get("kind") or "")
        if kind in {"judge", "llm_judge"} or (not kind and rubric) or entry.get("judge") is True:
            kind = "judge"
        else:
            kind = "rule"
        rule = str(entry.get("rule") or entry.get("scorer") or (entry.get("name") if kind == "rule" else "") or "")
        key = str(entry.get("id") or entry.get("version_id") or f"{kind}-{index}-{metric}")
        specs.append(
            EvaluatorSpec(
                key=key,
                kind=kind,
                metric=metric,
                direction=direction,
                rule=rule,
                config=dict(entry.get("config") or {}),
                version_id=entry.get("version_id") or entry.get("id"),
                rubric=rubric,
                threshold=float(entry.get("threshold", 0.7)),
                model=entry.get("model"),
            )
        )
    if not specs:
        raise InvalidArgumentError("at least one evaluator version is required")
    return specs


@dataclass(frozen=True)
class _ScoreDraft:
    metric_name: str
    value: float
    passed: bool | None
    details: dict[str, Any]
    evaluator_version_id: str | None


@dataclass(frozen=True)
class _JudgeDraft:
    evaluator_version_id: str | None
    model: str
    prompt_hash: str
    status: str
    score: float | None
    request: dict[str, Any]
    response: dict[str, Any]
    parsed: dict[str, Any]
    error: str | None
    latency_ms: int
    cost_usd: float
    raw_ref: str | None


@dataclass(frozen=True)
class _Invocation:
    item_id: str
    status: str
    output: str | None = None
    error: str | None = None
    latency_ms: int = 0
    cost_usd: float = 0.0
    raw_ref: str | None = None
    trace_id: str | None = None
    scores: list[_ScoreDraft] = field(default_factory=list)
    judge_calls: list[_JudgeDraft] = field(default_factory=list)


class _ScoringFailure(Exception):
    def __init__(
        self,
        error: str,
        *,
        scores: list[_ScoreDraft],
        judge_calls: list[_JudgeDraft],
        cost_usd: float,
    ) -> None:
        super().__init__(error)
        self.error = error
        self.scores = scores
        self.judge_calls = judge_calls
        self.cost_usd = cost_usd


def _input_text(payload: dict[str, Any]) -> str:
    value = payload.get("input", payload.get("prompt", payload))
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _error_text(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {exc}"[:1000]


class RunExecutor:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        adapter: TargetAdapter | None = None,
        judge_gateway: JudgeModelGateway | None = None,
        artifact_store: Any = None,
        max_workers: int = 1,
    ) -> None:
        if max_workers < 1:
            raise InvalidArgumentError("max_workers must be at least 1")
        self._session_factory = session_factory
        self._adapter = adapter
        self._judge_gateway = judge_gateway
        self._artifact_store = artifact_store
        self._max_workers = max_workers

    def cancel(self, ctx: TenantContext, run_id: str) -> RunView:
        with self._session_factory() as session:
            run = self._get_run(session, ctx, run_id)
            if run.status not in _TERMINAL:
                run.status = "cancelled"
                run.finished_at = utcnow_naive()
            view = run_view(session, run)
            session.commit()
            return view

    def execute(self, ctx: TenantContext, run_id: str) -> RunView:
        with self._session_factory() as session:
            run = self._get_run(session, ctx, run_id)
            if run.status in _TERMINAL:
                return run_view(session, run)
            if run.status == "paused_budget":
                run.status = "running"
                run.error = None
            else:
                run.status = "running"
            if run.started_at is None:
                run.started_at = utcnow_naive()
            if is_over_budget(run.cost_usd, run.budget_usd):
                run.status = "paused_budget"
                run.error = "budget exceeded"
            session.commit()
            specs = parse_evaluator_specs(run.manifest or {})
            mode = run.mode
            manifest = run.manifest or {}
            if mode == "replay":
                active_adapter: TargetAdapter = ReplayAdapter(self._artifact_store)
            else:
                if self._adapter is None:
                    raise InvalidArgumentError("a target adapter is required for record runs")
                active_adapter = self._adapter
            status = run.status

        if status == "paused_budget":
            with self._session_factory() as session:
                return run_view(session, self._get_run(session, ctx, run_id))

        while True:
            current = self._status(ctx, run_id)
            if current != "running":
                with self._session_factory() as session:
                    return run_view(session, self._get_run(session, ctx, run_id))
            with self._session_factory() as session:
                run = self._get_run(session, ctx, run_id)
                if is_over_budget(run.cost_usd, run.budget_usd):
                    run.status = "paused_budget"
                    run.error = "budget exceeded"
                    session.commit()
                    return run_view(session, run)
                batch = list(
                    session.scalars(
                        select(RunItem)
                        .where(
                            RunItem.tenant_id == ctx.tenant_id,
                            RunItem.run_id == run_id,
                            RunItem.status == "pending",
                        )
                        .order_by(RunItem.sample_index, RunItem.id)
                        .limit(self._max_workers)
                    )
                )
            if not batch:
                break
            invocations = self._invoke_batch(ctx, batch, manifest, specs, active_adapter)
            for _item, invocation in zip(batch, invocations, strict=True):
                with self._session_factory() as session:
                    run = self._get_run(session, ctx, run_id)
                    row = session.get(RunItem, invocation.item_id)
                    if row is None or row.status != "pending":
                        continue
                    self._apply(session, run, row, invocation)
                    session.commit()
            if self._status(ctx, run_id) == "cancelled":
                with self._session_factory() as session:
                    return run_view(session, self._get_run(session, ctx, run_id))
            with self._session_factory() as session:
                run = self._get_run(session, ctx, run_id)
                if is_over_budget(run.cost_usd, run.budget_usd):
                    run.status = "paused_budget"
                    run.error = "budget exceeded"
                    session.commit()
                    return run_view(session, run)

        with self._session_factory() as session:
            run = self._get_run(session, ctx, run_id)
            if run.status == "running":
                if run.failed_items > 0 and run.succeeded_items == 0:
                    run.status = "failed"
                else:
                    run.status = "succeeded"
                run.finished_at = utcnow_naive()
                run.progress = 100
            view = run_view(session, run)
            session.commit()
            return view

    def _invoke_batch(
        self,
        ctx: TenantContext,
        batch: list[RunItem],
        manifest: dict[str, Any],
        specs: list[EvaluatorSpec],
        adapter: TargetAdapter,
    ) -> list[_Invocation]:
        if self._max_workers == 1 or len(batch) == 1:
            return [self._invoke_one(ctx, item, manifest, specs, adapter) for item in batch]
        with ThreadPoolExecutor(max_workers=self._max_workers) as pool:
            return list(pool.map(lambda item: self._invoke_one(ctx, item, manifest, specs, adapter), batch))

    def _invoke_one(
        self,
        ctx: TenantContext,
        item: RunItem,
        manifest: dict[str, Any],
        specs: list[EvaluatorSpec],
        adapter: TargetAdapter,
    ) -> _Invocation:
        started = time.perf_counter()
        request = AgentRequest(
            sample_key=item.sample_key,
            payload=dict(item.payload or {}),
            expected=item.expected,
            trace_id=item.trace_id,
            raw_ref=item.raw_ref,
        )
        try:
            response = adapter.invoke(ctx, request)
        except Exception as exc:  # noqa: BLE001 - one item must not kill the run
            return _Invocation(
                item_id=item.id,
                status="failed",
                error=_error_text(exc),
                latency_ms=_elapsed_ms(started),
            )
        try:
            scores, judge_calls, judge_cost = self._score(ctx, item, response, manifest, specs)
        except _ScoringFailure as failure:
            return _Invocation(
                item_id=item.id,
                status="failed",
                output=response.output,
                error=failure.error,
                latency_ms=_elapsed_ms(started),
                cost_usd=float(response.cost_usd) + failure.cost_usd,
                raw_ref=response.raw_ref,
                trace_id=response.trace_id,
                scores=failure.scores,
                judge_calls=failure.judge_calls,
            )
        except Exception as exc:  # noqa: BLE001 - scoring failure is item-local
            return _Invocation(
                item_id=item.id,
                status="failed",
                output=response.output,
                error=_error_text(exc),
                latency_ms=_elapsed_ms(started),
                cost_usd=float(response.cost_usd),
                raw_ref=response.raw_ref,
                trace_id=response.trace_id,
            )
        return _Invocation(
            item_id=item.id,
            status="succeeded",
            output=response.output,
            latency_ms=_elapsed_ms(started),
            cost_usd=float(response.cost_usd) + judge_cost,
            raw_ref=response.raw_ref,
            trace_id=response.trace_id,
            scores=scores,
            judge_calls=judge_calls,
        )

    def _score(
        self,
        ctx: TenantContext,
        item: RunItem,
        response: AgentResponse,
        manifest: dict[str, Any],
        specs: list[EvaluatorSpec],
    ) -> tuple[list[_ScoreDraft], list[_JudgeDraft], float]:
        scores: list[_ScoreDraft] = []
        judge_calls: list[_JudgeDraft] = []
        judge_cost = 0.0
        expected = item.expected if item.expected is not None else (item.payload or {}).get("expected")
        for spec in specs:
            if spec.kind == "judge":
                if self._judge_gateway is None:
                    raise InvalidArgumentError("a judge gateway is required for judge evaluators")
                judge = JudgeEvaluator(self._judge_gateway, model=spec.model or "judge")
                started = time.perf_counter()
                try:
                    outcome = judge.evaluate(
                        ctx,
                        rubric=spec.rubric,
                        input_text=_input_text(item.payload or {}),
                        output_text=response.output,
                        threshold=spec.threshold,
                        model=spec.model,
                    )
                except Exception as exc:
                    judge_calls.append(
                        _JudgeDraft(
                            evaluator_version_id=spec.version_id,
                            model=spec.model or "judge",
                            prompt_hash=hashlib.sha256(canonical_json({"rubric": spec.rubric}).encode()).hexdigest(),
                            status="failed",
                            score=None,
                            request={"rubric": spec.rubric},
                            response={},
                            parsed={},
                            error=_error_text(exc),
                            latency_ms=_elapsed_ms(started),
                            cost_usd=0.0,
                            raw_ref=None,
                        )
                    )
                    raise _ScoringFailure(
                        _error_text(exc),
                        scores=scores,
                        judge_calls=judge_calls,
                        cost_usd=judge_cost,
                    ) from exc
                judge_cost += outcome.cost_usd
                judge_calls.append(_judge_draft(spec, outcome, item, _elapsed_ms(started)))
                scores.append(
                    _ScoreDraft(
                        metric_name=spec.metric,
                        value=outcome.score,
                        passed=outcome.passed,
                        details={"reasoning": outcome.reasoning, "label": outcome.parsed.get("label")},
                        evaluator_version_id=spec.version_id,
                    )
                )
            else:
                if expected is None:
                    raise InvalidArgumentError("expected value is required for rule scoring", sample=item.sample_key)
                result: RuleScore = score_rule(
                    spec.rule,
                    expected=expected,
                    actual=response.output,
                    config=spec.config,
                )
                scores.append(
                    _ScoreDraft(
                        metric_name=spec.metric,
                        value=result.value,
                        passed=result.passed,
                        details=result.details,
                        evaluator_version_id=spec.version_id,
                    )
                )
        return scores, judge_calls, judge_cost

    def _apply(self, session: Session, run: Run, item: RunItem, invocation: _Invocation) -> None:
        item.status = invocation.status
        item.output = invocation.output
        item.error = invocation.error
        item.latency_ms = invocation.latency_ms
        item.cost_usd = invocation.cost_usd
        item.raw_ref = invocation.raw_ref
        item.trace_id = invocation.trace_id or item.trace_id
        item.updated_at = utcnow_naive()
        for draft in invocation.scores:
            existing = session.scalar(
                select(Score).where(
                    Score.tenant_id == run.tenant_id,
                    Score.run_item_id == item.id,
                    Score.metric_name == draft.metric_name,
                )
            )
            if existing is None:
                session.add(
                    Score(
                        id=new_ulid(),
                        tenant_id=run.tenant_id,
                        run_id=run.id,
                        run_item_id=item.id,
                        metric_name=draft.metric_name,
                        value=draft.value,
                        passed=draft.passed,
                        details=draft.details,
                        evaluator_version_id=draft.evaluator_version_id,
                    )
                )
        for judge_draft in invocation.judge_calls:
            session.add(
                JudgeCall(
                    id=new_ulid(),
                    tenant_id=run.tenant_id,
                    run_id=run.id,
                    run_item_id=item.id,
                    evaluator_version_id=judge_draft.evaluator_version_id,
                    model=judge_draft.model,
                    prompt_hash=judge_draft.prompt_hash,
                    status=judge_draft.status,
                    score=judge_draft.score,
                    request=judge_draft.request,
                    response=judge_draft.response,
                    parsed=judge_draft.parsed,
                    error=judge_draft.error,
                    latency_ms=judge_draft.latency_ms,
                    cost_usd=judge_draft.cost_usd,
                    raw_ref=judge_draft.raw_ref,
                )
            )
        if invocation.status == "succeeded":
            run.succeeded_items += 1
        elif invocation.status == "skipped":
            run.skipped_items += 1
        else:
            run.failed_items += 1
        run.cost_usd = float(run.cost_usd) + float(invocation.cost_usd)
        done = run.succeeded_items + run.failed_items + run.skipped_items
        run.progress = min(100, int(round(done * 100 / run.total_items))) if run.total_items else 0

    def _status(self, ctx: TenantContext, run_id: str) -> str:
        with self._session_factory() as session:
            return self._get_run(session, ctx, run_id).status

    @staticmethod
    def _get_run(session: Session, ctx: TenantContext, run_id: str) -> Run:
        run = session.scalar(select(Run).where(Run.tenant_id == ctx.tenant_id, Run.id == run_id))
        if run is None:
            raise NotFoundError("Run not found")
        return run


def _elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)


def _judge_draft(spec: EvaluatorSpec, outcome: JudgeOutcome, item: RunItem, latency_ms: int) -> _JudgeDraft:
    return _JudgeDraft(
        evaluator_version_id=spec.version_id,
        model=outcome.model,
        prompt_hash=hashlib.sha256(canonical_json(outcome.prompt_messages).encode("utf-8")).hexdigest(),
        status="succeeded",
        score=outcome.score,
        request={"messages": outcome.prompt_messages, "sample_key": item.sample_key},
        response={"text": outcome.raw_text, "usage": outcome.usage, "raw_ref": outcome.raw_ref},
        parsed=outcome.parsed,
        error=None,
        latency_ms=latency_ms,
        cost_usd=outcome.cost_usd,
        raw_ref=outcome.raw_ref,
    )
