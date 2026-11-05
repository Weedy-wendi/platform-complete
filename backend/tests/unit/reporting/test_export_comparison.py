"""Comparison export formats (REP-06)."""

from __future__ import annotations

import csv
import io
import json
from xml.etree import ElementTree

import pytest

from app.core.errors import InvalidArgumentError
from app.modules.evaluation.public import ComparisonView, MetricComparison
from app.modules.reporting.public import ReportService


class FakeEvaluation:
    def __init__(self, comparison: ComparisonView) -> None:
        self.comparison = comparison
        self.calls: list[tuple[str, str]] = []

    def get_run(self, ctx, run_id: str):  # pragma: no cover - not used by export
        raise AssertionError("get_run should not be called")

    def list_items(self, ctx, run_id: str, query):  # pragma: no cover - not used by export
        raise AssertionError("list_items should not be called")

    def compare(self, ctx, run_a: str, run_b: str, metric_names=None) -> ComparisonView:
        self.calls.append((run_a, run_b))
        return self.comparison


def _comparison() -> ComparisonView:
    regression = MetricComparison(
        name="accuracy",
        baseline=1.0,
        candidate=0.5,
        delta=-0.5,
        delta_pct=-50.0,
        direction="higher_is_better",
        significant=True,
        ci_low=-0.6,
        ci_high=-0.4,
        baseline_n=10,
        candidate_n=10,
    )
    return ComparisonView(
        run_a="run-base",
        run_b="run-candidate",
        metrics=[regression],
        regressions=[regression],
        improvements=[],
        warnings=["runs use different suites"],
        comparable=True,
    )


def _service() -> tuple[ReportService, FakeEvaluation]:
    evaluation = FakeEvaluation(_comparison())
    return ReportService(None, evaluation=evaluation), evaluation  # type: ignore[arg-type]


def test_json_comparison_export_uses_baseline_and_candidate() -> None:
    service, evaluation = _service()
    payload = json.loads(service.export_comparison(None, "run-candidate", "run-base", "json"))  # type: ignore[arg-type]
    assert payload["run_a"] == "run-base"
    assert payload["run_b"] == "run-candidate"
    assert payload["regressions"][0]["name"] == "accuracy"
    assert evaluation.calls == [("run-base", "run-candidate")]


def test_csv_comparison_export_has_metric_rows_and_warnings() -> None:
    service, _ = _service()
    rows = list(
        csv.reader(io.StringIO(service.export_comparison(None, "run-candidate", "run-base", "csv").decode()))  # type: ignore[arg-type]
    )
    assert rows[0] == ["section", "key", "value"]
    assert ["comparison", "run_a", "run-base"] in rows
    assert ["comparison", "run_b", "run-candidate"] in rows
    assert ["metric", "metric.accuracy.delta", "-0.5"] in rows
    assert ["metric", "metric.accuracy.significant", "True"] in rows
    assert ["warning", "0", "runs use different suites"] in rows


def test_junit_comparison_export_marks_regressions() -> None:
    service, _ = _service()
    root = ElementTree.fromstring(service.export_comparison(None, "run-candidate", "run-base", "junit"))  # type: ignore[arg-type]
    assert root.tag == "testsuite"
    assert root.attrib["tests"] == "1"
    assert root.attrib["failures"] == "1"
    case = root.find("testcase")
    assert case is not None
    assert case.attrib["name"] == "accuracy"
    assert case.find("failure") is not None
    assert case.find("system-out") is not None


def test_unknown_comparison_export_format_is_rejected() -> None:
    service, evaluation = _service()
    with pytest.raises(InvalidArgumentError):
        service.export_comparison(None, "run-candidate", "run-base", "xml")  # type: ignore[arg-type]
    assert evaluation.calls == []
