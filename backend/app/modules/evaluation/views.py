"""Read projections for runs and items."""

from __future__ import annotations

import math
from collections import defaultdict
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.evaluation.models import Run, RunItem, Score
from app.modules.evaluation.types import MetricSummary, RunItemView, RunView, ScoreView


def _direction_map(run: Run) -> dict[str, str]:
    directions: dict[str, str] = {}
    manifest = run.manifest or {}
    for config in manifest.get("metric_configs", []) or []:
        if isinstance(config, dict):
            name = str(config.get("name") or config.get("metric") or "")
            if name:
                directions[name] = str(config.get("direction") or "higher_is_better")
    for version in manifest.get("evaluator_versions", []) or []:
        if not isinstance(version, dict):
            continue
        metric = version.get("metric")
        if isinstance(metric, dict) and metric.get("name"):
            directions.setdefault(str(metric["name"]), str(metric.get("direction") or "higher_is_better"))
        elif isinstance(metric, str):
            directions.setdefault(metric, str(version.get("direction") or "higher_is_better"))
    return directions


def _value(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def metric_summaries(session: Session, run: Run) -> list[MetricSummary]:
    rows = session.execute(
        select(Score.metric_name, Score.value).where(
            Score.tenant_id == run.tenant_id,
            Score.run_id == run.id,
        )
    )
    grouped: dict[str, list[float]] = defaultdict(list)
    for name, value in rows:
        grouped[str(name)].append(_value(value))
    directions = _direction_map(run)
    summaries: list[MetricSummary] = []
    for name in sorted(grouped):
        values = grouped[name]
        count = len(values)
        mean = sum(values) / count if count else 0.0
        if count > 1:
            variance = sum((value - mean) ** 2 for value in values) / (count - 1)
            stdev = math.sqrt(variance)
        else:
            stdev = 0.0
        summaries.append(
            MetricSummary(
                name=name,
                value=mean,
                count=count,
                stdev=stdev,
                direction=directions.get(name, "higher_is_better"),  # type: ignore[arg-type]
            )
        )
    return summaries


def run_view(session: Session, run: Run, *, metrics: list[MetricSummary] | None = None) -> RunView:
    done = run.succeeded_items + run.failed_items + run.skipped_items
    progress = int(round(done * 100 / run.total_items)) if run.total_items else 0
    return RunView(
        run_id=run.id,
        tenant_id=run.tenant_id,
        status=run.status,
        mode=run.mode,
        manifest_hash=run.manifest_hash,
        dataset_id=run.dataset_id,
        dataset_version=run.dataset_version,
        suite_id=run.suite_id,
        suite_version=run.suite_version,
        total_items=run.total_items,
        succeeded_items=run.succeeded_items,
        failed_items=run.failed_items,
        skipped_items=run.skipped_items,
        cost_usd=run.cost_usd,
        budget_usd=run.budget_usd,
        progress=min(progress, 100),
        created_at=run.created_at,
        started_at=run.started_at,
        finished_at=run.finished_at,
        error=run.error,
        metrics=metrics if metrics is not None else metric_summaries(session, run),
    )


def item_view(session: Session, item: RunItem) -> RunItemView:
    rows = session.scalars(
        select(Score).where(
            Score.tenant_id == item.tenant_id,
            Score.run_item_id == item.id,
        )
    )
    scores = [
        ScoreView(metric_name=row.metric_name, value=row.value, passed=row.passed, details=row.details or {})
        for row in rows
    ]
    return RunItemView(
        id=item.id,
        run_id=item.run_id,
        sample_key=item.sample_key,
        status=item.status,
        sample_index=item.sample_index,
        output=item.output,
        error=item.error,
        latency_ms=item.latency_ms,
        cost_usd=item.cost_usd,
        raw_ref=item.raw_ref,
        trace_id=item.trace_id,
        scores=scores,
    )
