"""Reports, read models and share links never cross tenant boundaries (012)."""

from __future__ import annotations

import pytest

from app.core.errors import InvalidArgumentError, NotFoundError
from app.modules.evaluation.service import EvaluationService
from app.modules.reporting.service import ReportReader, ReportService
from tests.integration.evaluation.support import FakeAdapter, sample, start_request


def _run(evaluation: EvaluationService, ctx, request_id: str = "r1"):
    run = evaluation.start_run(ctx, start_request((sample("s1", "yes"),), client_request_id=request_id))
    return evaluation.execute(ctx, run.run_id, adapter=FakeAdapter({"s1": "yes"}))


def test_cross_tenant_report_access_is_not_found(
    reports: ReportService, reader: ReportReader, ctx, other_ctx, evaluation
) -> None:
    run = _run(evaluation, ctx)
    reports.generate_run_report(ctx, run.run_id, "json")
    reports.refresh_read_model(ctx, run.run_id)

    with pytest.raises(NotFoundError):
        reader.get_run_report(other_ctx, run.run_id, "json")
    with pytest.raises(NotFoundError):
        reports.generate_run_report(other_ctx, run.run_id, "json")
    with pytest.raises(NotFoundError):
        reports.export(other_ctx, run.run_id, "csv")
    with pytest.raises(NotFoundError):
        reports.get_read_model(other_ctx, run.run_id)
    with pytest.raises(NotFoundError):
        reports.refresh_read_model(other_ctx, run.run_id)


def test_cross_tenant_comparison_is_not_found(reports: ReportService, ctx, other_ctx, evaluation) -> None:
    first = _run(evaluation, ctx, "a")
    second = _run(evaluation, ctx, "b")
    with pytest.raises(NotFoundError):
        reports.compare_report(other_ctx, first.run_id, second.run_id)


def test_share_link_rejects_wrong_tenant_and_expiry(reports: ReportService, ctx, other_ctx, evaluation) -> None:
    run = _run(evaluation, ctx)
    token = reports.create_share_link(ctx, run.run_id, secret="s3cret", ttl_seconds=60, now=1000.0)

    with pytest.raises(NotFoundError):
        reports.resolve_share_link(other_ctx, token, secret="s3cret", now=1001.0)
    assert reports.resolve_share_link(ctx, token, secret="s3cret", now=1001.0).run_id == run.run_id

    with pytest.raises(InvalidArgumentError):
        reports.resolve_share_link(ctx, token, secret="s3cret", now=2000.0)
    with pytest.raises(InvalidArgumentError):
        reports.resolve_share_link(ctx, token, secret="wrong", now=1001.0)
    with pytest.raises(InvalidArgumentError):
        reports.resolve_share_link(ctx, "not-a-token", secret="s3cret", now=1001.0)
