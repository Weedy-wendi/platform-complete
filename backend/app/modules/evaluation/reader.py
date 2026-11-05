"""Tenant-scoped run reader, pagination and statistical comparison."""

from __future__ import annotations

import base64
import json
import math
from datetime import datetime
from typing import Protocol

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.context import TenantContext
from app.core.errors import InvalidArgumentError, NotFoundError
from app.core.pagination import Page, clamp_limit
from app.modules.evaluation.models import Run, RunItem, Score
from app.modules.evaluation.types import (
    ComparisonView,
    MetricComparison,
    RunItemQuery,
    RunItemView,
    RunQuery,
    RunView,
)
from app.modules.evaluation.views import item_view, metric_summaries, run_view


def _encode_cursor(payload: dict[str, object]) -> str:
    return base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode()


def _decode_cursor(cursor: str) -> dict[str, object]:
    try:
        payload = json.loads(base64.urlsafe_b64decode(cursor.encode()))
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        raise InvalidArgumentError("invalid run cursor") from exc
    if not isinstance(payload, dict):
        raise InvalidArgumentError("invalid run cursor")
    return payload


class RunReaderProtocol(Protocol):
    def get_run(self, ctx: TenantContext, run_id: str) -> RunView: ...
    def list_items(self, ctx: TenantContext, run_id: str, query: RunItemQuery) -> Page[RunItemView]: ...


class RunReader:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def get_run(self, ctx: TenantContext, run_id: str) -> RunView:
        with self._session_factory() as session:
            return run_view(session, self._get_run(session, ctx, run_id))

    def list_runs(self, ctx: TenantContext, query: RunQuery | None = None) -> Page[RunView]:
        query = query or RunQuery()
        page_size = clamp_limit(query.limit, default=20, maximum=100)
        statement = select(Run).where(Run.tenant_id == ctx.tenant_id)
        if query.status:
            statement = statement.where(Run.status == query.status)
        if query.suite_id:
            statement = statement.where(Run.suite_id == query.suite_id)
        if query.cursor:
            payload = _decode_cursor(query.cursor)
            stamp = datetime.fromisoformat(str(payload["t"]))
            statement = statement.where(
                or_(Run.created_at < stamp, and_(Run.created_at == stamp, Run.id < str(payload["id"])))
            )
        statement = statement.order_by(Run.created_at.desc(), Run.id.desc()).limit(page_size + 1)
        with self._session_factory() as session:
            rows = list(session.scalars(statement))
            views = [run_view(session, row, metrics=metric_summaries(session, row)) for row in rows[:page_size]]
        next_cursor = (
            _encode_cursor({"t": rows[page_size - 1].created_at.isoformat(), "id": rows[page_size - 1].id})
            if len(rows) > page_size
            else None
        )
        return Page(items=views, next_cursor=next_cursor, truncated=len(rows) > page_size)

    def list_items(
        self,
        ctx: TenantContext,
        run_id: str,
        query: RunItemQuery | None = None,
    ) -> Page[RunItemView]:
        query = query or RunItemQuery()
        page_size = clamp_limit(query.limit, default=20, maximum=100)
        with self._session_factory() as session:
            self._get_run(session, ctx, run_id)
            statement = select(RunItem).where(
                RunItem.tenant_id == ctx.tenant_id,
                RunItem.run_id == run_id,
            )
            if query.status:
                statement = statement.where(RunItem.status == query.status)
            if query.metric:
                statement = statement.where(
                    RunItem.id.in_(
                        select(Score.run_item_id).where(
                            Score.tenant_id == ctx.tenant_id,
                            Score.run_id == run_id,
                            Score.metric_name == query.metric,
                        )
                    )
                )
            if query.cursor:
                payload = _decode_cursor(query.cursor)
                statement = statement.where(
                    or_(
                        RunItem.sample_index > int(str(payload["i"])),
                        and_(RunItem.sample_index == int(str(payload["i"])), RunItem.id > str(payload["id"])),
                    )
                )
            statement = statement.order_by(RunItem.sample_index, RunItem.id).limit(page_size + 1)
            rows = list(session.scalars(statement))
            items = [item_view(session, row) for row in rows[:page_size]]
        next_cursor = (
            _encode_cursor({"i": rows[page_size - 1].sample_index, "id": rows[page_size - 1].id})
            if len(rows) > page_size
            else None
        )
        return Page(items=items, next_cursor=next_cursor, truncated=len(rows) > page_size)

    def compare(
        self,
        ctx: TenantContext,
        run_a: str,
        run_b: str,
        metric_names: list[str] | None = None,
    ) -> ComparisonView:
        with self._session_factory() as session:
            baseline_row = self._get_run(session, ctx, run_a)
            candidate_row = self._get_run(session, ctx, run_b)
            baseline = run_view(session, baseline_row)
            candidate = run_view(session, candidate_row)
            baseline_manifest = baseline_row.manifest or {}
            candidate_manifest = candidate_row.manifest or {}
            baseline_hash = baseline_row.dataset_hash
            candidate_hash = candidate_row.dataset_hash

        warnings: list[str] = []
        if baseline.suite_id != candidate.suite_id:
            warnings.append("runs use different suites")
        if baseline.manifest_hash == candidate.manifest_hash:
            warnings.append("runs share the same manifest hash")
        if baseline.mode != candidate.mode:
            warnings.append("runs use different execution modes")

        comparable = True
        if baseline_hash != candidate_hash:
            comparable = False
            warnings.append("not_comparable: runs use different dataset hashes")
        for field in ("adapter_version", "target_config_version"):
            wrong = baseline_manifest.get(field)
            right = candidate_manifest.get(field)
            if wrong != right:
                comparable = False
                warnings.append(f"not_comparable: runs use different {field}")
        if not comparable:
            warnings.append("not_comparable")

        baseline_metrics = {summary.name: summary for summary in baseline.metrics}
        candidate_metrics = {summary.name: summary for summary in candidate.metrics}
        selected = metric_names or sorted(set(baseline_metrics) & set(candidate_metrics))
        if metric_names:
            for name in metric_names:
                if name not in baseline_metrics:
                    warnings.append(f"metric not available in baseline: {name}")
                if name not in candidate_metrics:
                    warnings.append(f"metric not available in candidate: {name}")

        comparisons: list[MetricComparison] = []
        for name in selected:
            left = baseline_metrics.get(name)
            right = candidate_metrics.get(name)
            if left is None or right is None:
                if not metric_names:
                    warnings.append(f"metric not available in both runs: {name}")
                continue
            delta = right.value - left.value
            delta_pct = (delta / abs(left.value) * 100.0) if left.value != 0 else 0.0
            significant = False
            ci_low: float | None = None
            ci_high: float | None = None
            if left.count >= 2 and right.count >= 2:
                standard_error = math.sqrt(left.stdev**2 / left.count + right.stdev**2 / right.count)
                ci_low = delta - 1.96 * standard_error
                ci_high = delta + 1.96 * standard_error
                significant = (ci_low > 0.0 or ci_high < 0.0) and comparable
            else:
                warnings.append(f"insufficient samples for metric: {name}")
            if comparable and delta != 0.0 and not significant:
                warnings.append(f"change is not statistically significant: {name}")
            comparisons.append(
                MetricComparison(
                    name=name,
                    baseline=left.value,
                    candidate=right.value,
                    delta=delta,
                    delta_pct=delta_pct,
                    direction=left.direction,
                    significant=significant,
                    ci_low=ci_low,
                    ci_high=ci_high,
                    baseline_n=left.count,
                    candidate_n=right.count,
                )
            )

        regressions = [item for item in comparisons if _is_regression(item.direction, item.delta) and item.delta != 0.0]
        improvements = [
            item for item in comparisons if not _is_regression(item.direction, item.delta) and item.significant
        ]
        return ComparisonView(
            run_a=run_a,
            run_b=run_b,
            metrics=comparisons,
            regressions=regressions,
            improvements=improvements,
            warnings=warnings,
            comparable=comparable,
        )

    @staticmethod
    def _get_run(session: Session, ctx: TenantContext, run_id: str) -> Run:
        run = session.scalar(select(Run).where(Run.tenant_id == ctx.tenant_id, Run.id == run_id))
        if run is None:
            raise NotFoundError("Run not found")
        return run


def _is_regression(direction: str, delta: float) -> bool:
    if direction == "lower_is_better":
        return delta > 0.0
    return delta < 0.0
