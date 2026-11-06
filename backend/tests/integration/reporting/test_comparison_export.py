"""Comparison exports across JSON/CSV/JUnit and tenant boundaries (REP-06)."""

from __future__ import annotations

import csv
import io
import json
from xml.etree import ElementTree

import pytest

from app.core.context import TenantContext
from app.core.errors import InvalidArgumentError, NotFoundError
from app.modules.evaluation.service import EvaluationService
from app.modules.evaluation.types import RunView
from app.modules.reporting.public import ReportService
from tests.integration.evaluation.support import FakeAdapter, sample, start_request


def _run(
    evaluation: EvaluationService,
    ctx: TenantContext,
    outputs: dict[str, str],
    *,
    client_request_id: str,
) -> RunView:
    samples = tuple(sample(f"s{index}", "yes") for index in range(3))
    run = evaluation.start_run(ctx, start_request(samples, client_request_id=client_request_id))
    return evaluation.execute(ctx, run.run_id, adapter=FakeAdapter(outputs))


def test_export_comparison_json_csv_and_junit(reports: ReportService, ctx, evaluation) -> None:
    baseline = _run(evaluation, ctx, {"s0": "yes", "s1": "yes", "s2": "yes"}, client_request_id="base")
    candidate = _run(evaluation, ctx, {"s0": "no", "s1": "no", "s2": "no"}, client_request_id="cand")

    payload = json.loads(reports.export_comparison(ctx, candidate.run_id, baseline.run_id, "json"))
    assert payload["run_a"] == baseline.run_id
    assert payload["run_b"] == candidate.run_id
    assert payload["regressions"][0]["name"] == "accuracy"

    text = reports.export_comparison(ctx, candidate.run_id, baseline.run_id, "csv").decode()
    parsed = list(csv.reader(io.StringIO(text)))
    assert parsed[0] == ["section", "key", "value"]
    assert ["comparison", "run_b", candidate.run_id] in parsed
    assert any(row[0] == "metric" and row[1] == "metric.accuracy.delta" for row in parsed)

    root = ElementTree.fromstring(reports.export_comparison(ctx, candidate.run_id, baseline.run_id, "junit"))
    assert root.tag == "testsuite"
    assert root.attrib["tests"] == "1"
    assert root.attrib["failures"] == "1"

    with pytest.raises(InvalidArgumentError):
        reports.export_comparison(ctx, candidate.run_id, baseline.run_id, "xml")


def test_export_comparison_rejects_cross_tenant_run(reports: ReportService, ctx, evaluation) -> None:
    baseline = _run(evaluation, ctx, {"s0": "yes", "s1": "yes", "s2": "yes"}, client_request_id="base")
    other = TenantContext(tenant_id="tenant-b", subject_id="user:2", scopes=frozenset(), trace_id="trace-2")
    foreign = evaluation.start_run(
        other,
        start_request((sample("s0", "yes"),), client_request_id="foreign"),
    )

    with pytest.raises(NotFoundError):
        reports.export_comparison(ctx, foreign.run_id, baseline.run_id, "json")
    with pytest.raises(NotFoundError):
        reports.export_comparison(ctx, baseline.run_id, foreign.run_id, "csv")
