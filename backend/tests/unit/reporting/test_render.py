"""Report rendering content and comparison summaries (REP-02/03)."""

from __future__ import annotations

import json
from datetime import datetime

from app.modules.evaluation.public import (
    ComparisonView,
    MetricComparison,
    MetricSummary,
    RunItemView,
    RunView,
    ScoreView,
)
from app.modules.reporting.render import (
    comparison_payload,
    content_hash,
    render_comparison_json,
    render_comparison_markdown,
    render_run_json,
    render_run_markdown,
)

_NOW = datetime(2026, 1, 1, 12, 0, 0)


def _run() -> RunView:
    return RunView(
        run_id="run-1",
        tenant_id="tenant-a",
        status="succeeded",
        mode="record",
        manifest_hash="b" * 64,
        dataset_id="dataset-1",
        dataset_version=1,
        suite_id="suite-1",
        suite_version=2,
        total_items=2,
        succeeded_items=1,
        failed_items=1,
        skipped_items=0,
        cost_usd=0.25,
        budget_usd=1.0,
        progress=100,
        created_at=_NOW,
        started_at=_NOW,
        finished_at=_NOW,
        error=None,
        metrics=[MetricSummary("accuracy", 0.5, count=2, stdev=0.5, direction="higher_is_better")],
    )


def _items() -> list[RunItemView]:
    return [
        RunItemView(
            id="item-1",
            run_id="run-1",
            sample_key="s1",
            status="succeeded",
            sample_index=0,
            output="yes",
            scores=[ScoreView("accuracy", 1.0, True)],
        ),
        RunItemView(
            id="item-2",
            run_id="run-1",
            sample_key="s2",
            status="failed",
            sample_index=1,
            error="TimeoutError: boom",
        ),
    ]


def test_json_report_matches_run() -> None:
    content = render_run_json(_run(), _items())
    payload = json.loads(content)
    assert payload["run"]["run_id"] == "run-1"
    assert payload["run"]["manifest_hash"] == "b" * 64
    assert payload["metrics"][0]["name"] == "accuracy"
    assert payload["items"][1]["error"] == "TimeoutError: boom"
    assert content_hash(content) == content_hash(render_run_json(_run(), _items()))


def test_markdown_report_includes_metrics_and_failures() -> None:
    content = render_run_markdown(_run(), _items())
    assert "# Run run-1" in content
    assert "accuracy" in content
    assert "0.500000" in content
    assert "Failed items" in content
    assert "TimeoutError: boom" in content


def _comparison() -> ComparisonView:
    regression = MetricComparison(
        "accuracy",
        1.0,
        0.5,
        -0.5,
        -50.0,
        "higher_is_better",
        True,
        -0.6,
        -0.4,
        10,
        10,
    )
    return ComparisonView(
        run_a="run-a",
        run_b="run-b",
        metrics=[regression],
        regressions=[regression],
        improvements=[],
        warnings=["runs use different suites"],
        comparable=True,
    )


def test_comparison_payload_and_markdown() -> None:
    payload = comparison_payload(_comparison())
    assert payload["regressions"][0]["name"] == "accuracy"
    assert payload["metrics"][0]["ci_low"] == -0.6
    content = render_comparison_markdown(_comparison())
    assert "Regressions" in content
    assert "accuracy" in content
    assert "runs use different suites" in content
    assert json.loads(render_comparison_json(_comparison()))["warnings"]
