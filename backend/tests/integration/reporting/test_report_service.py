"""Snapshot generation, comparison, export and share links (REP-01..05)."""

from __future__ import annotations

import csv
import io
import json
from xml.etree import ElementTree

import pytest
from sqlalchemy import func, select

from app.core.errors import InvalidArgumentError
from app.modules.evaluation.service import EvaluationService
from app.modules.evaluation.types import RunView
from app.modules.reporting.models import ReportSnapshot
from app.modules.reporting.service import ReportReader, ReportService
from tests.integration.evaluation.support import FakeAdapter, sample, start_request


def _run(
    evaluation: EvaluationService,
    ctx,
    outputs: dict[str, str],
    *,
    client_request_id: str,
    sample_count: int = 3,
    fail_on: set[str] | None = None,
) -> RunView:
    samples = tuple(sample(f"s{index}", "yes") for index in range(sample_count))
    run = evaluation.start_run(ctx, start_request(samples, client_request_id=client_request_id))
    return evaluation.execute(ctx, run.run_id, adapter=FakeAdapter(outputs, fail_on=fail_on))


def test_json_and_markdown_snapshot_match_run(reports: ReportService, ctx, evaluation, factory) -> None:
    run = _run(
        evaluation,
        ctx,
        {"s0": "yes", "s1": "no", "s2": "yes"},
        client_request_id="r1",
        fail_on={"s1"},
    )
    report = reports.generate_run_report(ctx, run.run_id, "json")
    payload = json.loads(report.content)
    assert report.run_id == run.run_id
    assert report.manifest_hash == run.manifest_hash
    assert payload["run"]["manifest_hash"] == run.manifest_hash
    assert payload["metrics"][0]["name"] == "accuracy"
    assert len(payload["items"]) == 3

    markdown = reports.generate_run_report(ctx, run.run_id, "markdown")
    assert "# Run " in markdown.content
    assert "accuracy" in markdown.content
    assert "Failed items" in markdown.content

    with factory() as session:
        count = session.scalar(select(func.count()).select_from(ReportSnapshot))
    assert count == 2


def test_snapshot_is_immutable_and_reader_reuses_it(
    reports: ReportService, reader: ReportReader, ctx, evaluation
) -> None:
    run = _run(evaluation, ctx, {"s0": "yes", "s1": "yes"}, client_request_id="r1", sample_count=2)
    first = reports.generate_run_report(ctx, run.run_id, "json")
    second = reports.generate_run_report(ctx, run.run_id, "json")
    assert first.content == second.content
    assert first.generated_at == second.generated_at
    assert reader.get_run_report(ctx, run.run_id, "json").content == first.content

    transient = reader.get_run_report(ctx, run.run_id, "markdown")
    assert transient.format == "markdown"
    assert transient.content.startswith("# Run")


def test_read_model_refresh(reports: ReportService, ctx, evaluation) -> None:
    run = _run(evaluation, ctx, {"s0": "yes", "s1": "yes"}, client_request_id="r1", sample_count=2)
    model = reports.refresh_read_model(ctx, run.run_id)
    assert model.status == "succeeded"
    assert model.total_items == 2
    assert model.succeeded_items == 2
    assert model.metrics[0]["name"] == "accuracy"
    again = reports.refresh_read_model(ctx, run.run_id)
    assert again.run_id == model.run_id
    assert reports.get_read_model(ctx, run.run_id).total_items == 2


def test_comparison_report_lists_regressions(reports: ReportService, ctx, evaluation) -> None:
    baseline = _run(evaluation, ctx, {"s0": "yes", "s1": "yes", "s2": "yes"}, client_request_id="base")
    candidate = _run(evaluation, ctx, {"s0": "no", "s1": "no", "s2": "no"}, client_request_id="cand")
    report = reports.compare_report(ctx, baseline.run_id, candidate.run_id)
    assert report.run_a == baseline.run_id
    assert report.metrics[0]["name"] == "accuracy"
    assert report.regressions[0]["delta"] == pytest.approx(-1.0)
    assert any("same manifest hash" in warning for warning in report.warnings)
    markdown = reports.render_comparison(ctx, baseline.run_id, candidate.run_id)
    assert "Regressions" in markdown
    json_text = reports.render_comparison(ctx, baseline.run_id, candidate.run_id, "json")
    assert json.loads(json_text)["regressions"]


def test_export_json_csv_and_junit(reports: ReportService, ctx, evaluation) -> None:
    run = _run(
        evaluation,
        ctx,
        {"s0": "yes", "s1": "no", "s2": "yes"},
        client_request_id="r1",
        fail_on={"s1"},
    )
    json_bytes = reports.export(ctx, run.run_id, "json")
    assert json.loads(json_bytes)["run"]["run_id"] == run.run_id

    csv_bytes = reports.export(ctx, run.run_id, "csv")
    rows = list(csv.reader(io.StringIO(csv_bytes.decode())))
    assert rows[0] == ["section", "key", "value"]
    assert any(row[0] == "metric" and row[1] == "accuracy.value" for row in rows)
    assert any(row[0] == "item" and row[1] == "s1.status" for row in rows)

    junit_bytes = reports.export(ctx, run.run_id, "junit")
    root = ElementTree.fromstring(junit_bytes)
    assert root.tag == "testsuite"
    assert root.attrib["tests"] == "3"
    assert root.attrib["failures"] == "1"

    streamed = b"".join(reports.iter_export(ctx, run.run_id, "csv"))
    assert b"accuracy.value" in streamed
    with pytest.raises(InvalidArgumentError):
        reports.export(ctx, run.run_id, "xml")


def test_share_link_roundtrip_and_expiry(reports: ReportService, ctx, evaluation) -> None:
    run = _run(evaluation, ctx, {"s0": "yes"}, client_request_id="r1", sample_count=1)
    token = reports.create_share_link(ctx, run.run_id, secret="s3cret", fmt="markdown", ttl_seconds=60, now=1000.0)
    target = reports.read_share_link(token, secret="s3cret", now=1001.0)
    assert target.run_id == run.run_id
    assert target.tenant_id == "tenant-a"
    assert target.format == "markdown"

    with pytest.raises(InvalidArgumentError):
        reports.read_share_link(token, secret="s3cret", now=2000.0)
    with pytest.raises(InvalidArgumentError):
        reports.read_share_link(token, secret="wrong", now=1001.0)
    with pytest.raises(InvalidArgumentError):
        reports.create_share_link(ctx, run.run_id, secret="s3cret", ttl_seconds=0)
