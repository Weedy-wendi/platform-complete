"""Reproducibility guardrails (QUAL-06 / FR-002).

The suite is deliberately in-process: SQLite plus deterministic fakes keep it
fast enough to run on every change, while still exercising the public module
surfaces used in production.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine

from app.core.context import TenantContext
from app.core.db import Base, make_session_factory
from app.core.errors import InvalidArgumentError
from app.modules.catalog.public import CatalogService, SchemaField
from app.modules.evaluation.public import (
    AgentRequest,
    AgentResponse,
    EvaluationService,
    JudgeEvaluator,
    JudgeModelRequest,
    JudgeModelResponse,
    SampleInput,
    StartRunRequest,
    calibration_report,
    cohen_kappa,
    require_calibrated,
)

_EVALUATION_TABLES = (
    "evaluator",
    "evaluator_version",
    "metric",
    "eval_suite",
    "suite_version",
    "target",
    "run",
    "run_item",
    "score",
    "judge_call",
    "baseline",
)
_CATALOG_TABLES = ("project", "dataset", "dataset_version", "sample")


@pytest.fixture()
def session_factory():
    engine = create_engine("sqlite://")
    tables = [Base.metadata.tables[name] for name in (*_EVALUATION_TABLES, *_CATALOG_TABLES)]
    Base.metadata.create_all(engine, tables=tables)
    try:
        yield make_session_factory(engine)
    finally:
        engine.dispose()


@pytest.fixture()
def ctx() -> TenantContext:
    return TenantContext(tenant_id="tenant-a", subject_id="user:1", scopes=frozenset(), trace_id="trace-1")


class DeterministicAdapter:
    def __init__(self, outputs: dict[str, str]) -> None:
        self._outputs = outputs

    def invoke(self, ctx: TenantContext, request: AgentRequest) -> AgentResponse:
        return AgentResponse(output=self._outputs.get(request.sample_key, ""), trace_id=f"trace-{request.sample_key}")


def _request(client_request_id: str) -> StartRunRequest:
    samples = tuple(SampleInput(f"s{index}", {"input": f"question {index}"}, expected="yes") for index in range(3))
    return StartRunRequest(
        client_request_id=client_request_id,
        dataset_id="dataset-1",
        dataset_version=1,
        dataset_hash="a" * 64,
        samples=samples,
        target_config={"adapter": "fake", "model": "fake-1", "temperature": 0.0, "seed": 7},
        evaluator_versions=(
            {
                "id": "ev-accuracy",
                "kind": "rule",
                "rule": "exact_match",
                "metric": {"name": "accuracy", "direction": "higher_is_better"},
            },
        ),
        metric_configs=({"name": "accuracy", "direction": "higher_is_better"},),
        sampling={"strategy": "full", "seed": 42},
        code_version="code-1",
        env="test",
    )


def test_same_manifest_replayed_five_times_is_identical(session_factory, ctx) -> None:
    service = EvaluationService(session_factory, max_workers=1)
    adapter = DeterministicAdapter({"s0": "yes", "s1": "no", "s2": "yes"})
    hashes: set[str] = set()
    values: list[tuple[str, float, int]] = []

    for index in range(5):
        run = service.start_run(ctx, _request(f"replay-{index}"))
        result = service.execute(ctx, run.run_id, adapter=adapter)
        assert result.status == "succeeded"
        hashes.add(result.manifest_hash)
        values.extend((metric.name, metric.value, metric.count) for metric in result.metrics)

    assert len(hashes) == 1
    assert values, "the run should expose at least one metric"
    assert all(value == values[0] for value in values)
    assert values[0][0] == "accuracy"


def test_repeated_judge_calls_are_within_tolerance(ctx) -> None:
    judge = JudgeEvaluator(
        _FixedGateway('{"score": 0.82, "reasoning": "clear and correct"}'),
        model="judge-fixed",
    )
    scores = [judge.evaluate(ctx, rubric="Be correct", input_text="2+2?", output_text="4").score for _ in range(5)]
    assert max(scores) - min(scores) <= 0.05


class _FixedGateway:
    def __init__(self, text: str) -> None:
        self._text = text

    def complete(self, ctx: TenantContext, request: JudgeModelRequest) -> JudgeModelResponse:
        return JudgeModelResponse(text=self._text)


def test_calibration_gate_accepts_well_agreed_labels_and_rejects_poor_ones() -> None:
    labels_a = ["pass"] * 10 + ["fail"] * 10
    labels_b = list(labels_a)
    labels_b[0] = "fail"
    labels_b[10] = "pass"

    report = calibration_report(labels_a, labels_b)
    assert cohen_kappa(labels_a, labels_b) == pytest.approx(0.8)
    assert report.kappa >= 0.7
    require_calibrated(report)

    poor_a = ["pass"] * 10 + ["fail"] * 10
    poor_b = ["pass"] * 7 + ["fail"] * 3 + ["pass"] * 5 + ["fail"] * 5
    poor = calibration_report(poor_a, poor_b)
    assert poor.kappa < 0.7
    with pytest.raises(InvalidArgumentError):
        require_calibrated(poor)


def test_dataset_version_is_immutable(session_factory, ctx) -> None:
    catalog = CatalogService(session_factory)
    project = catalog.create_project(ctx, "Repro project")
    dataset = catalog.create_dataset(ctx, project_id=project.id, name="Repro dataset")
    samples = [
        {"sample_key": "1", "payload": {"q": "a", "answer": "b"}},
        {"sample_key": "2", "payload": {"q": "c", "answer": "d"}},
    ]
    schema = [SchemaField("q", "string"), SchemaField("answer", "string")]

    first = catalog.publish_version(ctx, dataset.id, samples, schema_fields=schema)
    duplicate = catalog.publish_version(ctx, dataset.id, list(reversed(samples)))
    assert duplicate.version == first.version
    assert duplicate.content_hash == first.content_hash

    second = catalog.publish_version(ctx, dataset.id, [{"sample_key": "1", "payload": {"q": "new"}}])
    assert second.version == first.version + 1

    original = catalog.get_version(ctx, first)
    assert original.row_count == 2
    assert original.ref.content_hash == first.content_hash
    assert not hasattr(catalog, "update_version")
