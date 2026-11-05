"""Evaluator versions, suites, targets and frozen baselines (EVL-01/04)."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.core.errors import InvalidArgumentError
from app.modules.evaluation.models import EvaluatorVersion
from app.modules.evaluation.service import EvaluationService
from tests.integration.evaluation.support import FakeAdapter, sample, start_request


def test_evaluator_versions_are_append_only(service: EvaluationService, ctx) -> None:
    evaluator = service.create_evaluator(ctx, "exact", kind="rule", config={"rule": "exact_match"})
    assert evaluator.latest_version == 1
    second = service.publish_evaluator_version(ctx, evaluator.id, {"rule": "contains"})
    assert second.version == 2
    third = service.publish_evaluator_version(ctx, evaluator.id, {"rule": "regex"})
    assert third.version == 3
    with pytest.raises(InvalidArgumentError):
        service.create_evaluator(ctx, "exact", kind="rule")
    with pytest.raises(InvalidArgumentError):
        service.publish_evaluator_version(ctx, evaluator.id, {})
    with pytest.raises(InvalidArgumentError):
        service.create_evaluator(ctx, "bad", kind="nope")


def test_suite_versions_bind_evaluator_versions(service: EvaluationService, ctx) -> None:
    evaluator = service.create_evaluator(ctx, "exact", config={"rule": "exact_match"})
    version = service.publish_evaluator_version(ctx, evaluator.id, {"rule": "exact_match", "case_sensitive": True})
    suite = service.create_suite(ctx, "smoke")
    first = service.publish_suite_version(
        ctx,
        suite.id,
        evaluator_versions=[{"id": version.id, "rule": "exact_match"}],
        metric_configs=[{"name": "accuracy", "direction": "higher_is_better"}],
    )
    second = service.publish_suite_version(
        ctx,
        suite.id,
        evaluator_versions=[{"id": version.id, "rule": "contains"}],
        metric_configs=[{"name": "accuracy", "direction": "higher_is_better"}],
    )
    assert (first.version, second.version) == (1, 2)
    assert second.evaluator_versions[0]["rule"] == "contains"
    with pytest.raises(InvalidArgumentError):
        service.create_suite(ctx, "smoke")
    with pytest.raises(InvalidArgumentError):
        service.publish_suite_version(ctx, suite.id, evaluator_versions=[], metric_configs=[])


def test_metric_direction_validation(service: EvaluationService, ctx) -> None:
    metric = service.create_metric(ctx, "latency", direction="lower_is_better")
    assert metric.direction == "lower_is_better"
    with pytest.raises(InvalidArgumentError):
        service.create_metric(ctx, "latency", direction="lower_is_better")
    with pytest.raises(InvalidArgumentError):
        service.create_metric(ctx, "bad", direction="sideways")


def test_target_config_is_versioned_and_validated(service: EvaluationService, ctx) -> None:
    target = service.create_target(
        ctx,
        "http-target",
        {
            "adapter": "http_json",
            "config_version": "cfg-1",
            "adapter_version": "v1",
            "url": "https://example.test/invoke",
        },
    )
    assert target.adapter == "http_json"
    assert target.config_version == "cfg-1"
    with pytest.raises(InvalidArgumentError):
        service.create_target(
            ctx,
            "http-target",
            {
                "adapter": "http_json",
                "config_version": "cfg-1",
                "adapter_version": "v1",
                "url": "https://example.test/invoke",
            },
        )
    with pytest.raises(InvalidArgumentError):
        service.create_target(
            ctx,
            "broken",
            {"adapter": "http_json", "config_version": "cfg-2", "headers": {"Authorization": "Bearer plain"}},
        )


def test_baseline_is_frozen(service: EvaluationService, ctx) -> None:
    first_samples = (sample("s1", "yes"),)
    first = service.start_run(ctx, start_request(first_samples, client_request_id="base-1"))
    service.execute(ctx, first.run_id, adapter=FakeAdapter({"s1": "yes"}))
    baseline = service.create_baseline(ctx, suite_id="suite-1", name="main", run_id=first.run_id)
    assert baseline.frozen is True
    assert baseline.manifest_hash == first.manifest_hash
    assert service.create_baseline(ctx, suite_id="suite-1", name="main", run_id=first.run_id).id == baseline.id

    second = service.start_run(
        ctx,
        start_request(first_samples, client_request_id="base-2"),
    )
    service.execute(ctx, second.run_id, adapter=FakeAdapter({"s1": "no"}))
    with pytest.raises(InvalidArgumentError):
        service.create_baseline(ctx, suite_id="suite-1", name="main", run_id=second.run_id)

    queued = service.start_run(ctx, start_request(first_samples, client_request_id="base-3"))
    with pytest.raises(InvalidArgumentError):
        service.create_baseline(ctx, suite_id="suite-1", name="other", run_id=queued.run_id)


def test_evaluator_version_rows_are_not_rewritten(service: EvaluationService, ctx, factory) -> None:
    evaluator = service.create_evaluator(ctx, "exact", config={"rule": "exact_match"})
    service.publish_evaluator_version(ctx, evaluator.id, {"rule": "contains"})
    with factory() as session:
        rows = list(
            session.scalars(
                select(EvaluatorVersion)
                .where(EvaluatorVersion.evaluator_id == evaluator.id)
                .order_by(EvaluatorVersion.version)
            )
        )
    assert [row.version for row in rows] == [1, 2]
    assert rows[0].config == {"rule": "exact_match"}
    assert rows[1].config == {"rule": "contains"}
    assert rows[0].config_hash != rows[1].config_hash
