"""Run reader pagination and comparison statistics (EVL-08/09)."""

from __future__ import annotations

import pytest

from app.modules.evaluation.service import EvaluationService
from app.modules.evaluation.types import RunItemQuery, RunQuery
from tests.integration.evaluation.support import FakeAdapter, sample, start_request


def _execute(
    service: EvaluationService,
    ctx,
    outputs: dict[str, str],
    *,
    client_request_id: str = "req-1",
    sample_count: int = 4,
    target_config_version: str = "cfg-1",
):
    samples = tuple(sample(f"s{index}", "yes") for index in range(sample_count))
    run = service.start_run(
        ctx,
        start_request(
            samples,
            client_request_id=client_request_id,
            target_config_version=target_config_version,
        ),
    )
    return service.execute(ctx, run.run_id, adapter=FakeAdapter(outputs))


def test_list_items_paginates(service: EvaluationService, ctx) -> None:
    run = _execute(service, ctx, {f"s{index}": "yes" for index in range(5)}, sample_count=5)
    collected = []
    cursor = None
    pages = 0
    while True:
        page = service.list_items(ctx, run.run_id, RunItemQuery(cursor=cursor, limit=2))
        collected.extend(page.items)
        pages += 1
        if not page.next_cursor:
            break
        cursor = page.next_cursor
    assert [item.sample_key for item in collected] == ["s0", "s1", "s2", "s3", "s4"]
    assert pages == 3


def test_list_items_filters_by_status_and_metric(service: EvaluationService, ctx) -> None:
    samples = tuple(sample(f"s{index}", "yes") for index in range(3))
    run = service.start_run(ctx, start_request(samples))
    service.execute(ctx, run.run_id, adapter=FakeAdapter(fail_on={"s1"}))
    failed = service.list_items(ctx, run.run_id, RunItemQuery(status="failed"))
    assert [item.sample_key for item in failed.items] == ["s1"]
    with_metric = service.list_items(ctx, run.run_id, RunItemQuery(metric="accuracy"))
    assert {item.sample_key for item in with_metric.items} == {"s0", "s2"}
    missing_metric = service.list_items(ctx, run.run_id, RunItemQuery(metric="missing"))
    assert missing_metric.items == []


def test_list_runs_paginates(service: EvaluationService, ctx) -> None:
    for index in range(3):
        service.start_run(ctx, start_request((sample("s1", "yes"),), client_request_id=f"r{index}"))
    first = service.list_runs(ctx, RunQuery(limit=2))
    assert len(first.items) == 2
    assert first.next_cursor
    second = service.list_runs(ctx, RunQuery(cursor=first.next_cursor, limit=2))
    assert len(second.items) == 1
    assert second.next_cursor is None


def test_compare_reports_delta_confidence_and_regressions(service: EvaluationService, ctx) -> None:
    baseline = _execute(service, ctx, {f"s{index}": "yes" for index in range(4)}, client_request_id="base")
    candidate = _execute(service, ctx, {f"s{index}": "no" for index in range(4)}, client_request_id="cand")

    comparison = service.compare(ctx, baseline.run_id, candidate.run_id)
    assert comparison.comparable is True
    assert len(comparison.metrics) == 1
    metric = comparison.metrics[0]
    assert metric.name == "accuracy"
    assert metric.baseline == pytest.approx(1.0)
    assert metric.candidate == pytest.approx(0.0)
    assert metric.delta == pytest.approx(-1.0)
    assert metric.delta_pct == pytest.approx(-100.0)
    assert metric.significant is True
    assert metric.ci_low is not None and metric.ci_high is not None
    assert metric.ci_high < 0
    assert [item.name for item in comparison.regressions] == ["accuracy"]
    assert "runs share the same manifest hash" in comparison.warnings


def test_compare_marks_version_mismatch_not_comparable(service: EvaluationService, ctx) -> None:
    baseline = _execute(service, ctx, {"s0": "yes"}, client_request_id="base", sample_count=1)
    candidate = _execute(
        service,
        ctx,
        {"s0": "yes"},
        client_request_id="cand",
        sample_count=1,
        target_config_version="cfg-2",
    )
    comparison = service.compare(ctx, baseline.run_id, candidate.run_id)
    assert comparison.comparable is False
    assert any("not_comparable" in warning for warning in comparison.warnings)
    assert comparison.metrics[0].significant is False


def test_compare_missing_metric_warns(service: EvaluationService, ctx) -> None:
    baseline = _execute(service, ctx, {"s0": "yes"}, client_request_id="base", sample_count=1)
    candidate = _execute(service, ctx, {"s0": "yes"}, client_request_id="cand", sample_count=1)
    comparison = service.compare(ctx, baseline.run_id, candidate.run_id, metric_names=["missing"])
    assert comparison.metrics == []
    assert any("missing" in warning for warning in comparison.warnings)
