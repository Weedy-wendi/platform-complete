"""End-to-end gate evaluation and evidence (GAT-02/03/04)."""

from __future__ import annotations

import pytest

from app.core.errors import InvalidArgumentError
from app.modules.evaluation.service import EvaluationService
from app.modules.evaluation.types import RunView
from app.modules.gate.service import GateService
from tests.integration.evaluation.support import FakeAdapter, sample, start_request


def _run(
    evaluation: EvaluationService,
    ctx,
    outputs: dict[str, str],
    *,
    client_request_id: str,
    sample_count: int = 3,
) -> RunView:
    samples = tuple(sample(f"s{index}", "yes") for index in range(sample_count))
    run = evaluation.start_run(ctx, start_request(samples, client_request_id=client_request_id))
    return evaluation.execute(ctx, run.run_id, adapter=FakeAdapter(outputs))


def test_gate_allow_with_evidence(gates: GateService, ctx, evaluation: EvaluationService) -> None:
    gate = gates.create_gate(ctx, "suite-1", "quality")
    gates.add_rule(ctx, gate.id, name="accuracy floor", kind="absolute", metric="accuracy", threshold=0.9)
    gates.add_rule(ctx, gate.id, name="enough data", kind="min_samples", min_samples=2)
    run = _run(evaluation, ctx, {"s0": "yes", "s1": "yes", "s2": "yes"}, client_request_id="r1")

    result = gates.evaluate(ctx, run.run_id, gate.id)
    assert result.status == "passed"
    assert result.passed is True
    assert result.manifest_hash == run.manifest_hash
    assert len(result.rules) == 2
    assert all(rule.evidence_ref for rule in result.rules)
    assert all(rule.expected and rule.actual for rule in result.rules)
    assert result.rules[0].actual.startswith("accuracy=1.000000")

    read = gates.read_gate(ctx, "suite-1", run.run_id)
    assert read is not None
    assert read.status == "passed"
    assert read.gate_id == gate.id
    assert gates.read_gate_for_gate(ctx, gate.id, run.run_id) is not None


def test_gate_deny_marks_rule_failure(gates: GateService, ctx, evaluation: EvaluationService) -> None:
    gate = gates.create_gate(ctx, "suite-1", "strict")
    gates.add_rule(ctx, gate.id, name="accuracy floor", kind="absolute", metric="accuracy", threshold=1.1)
    run = _run(evaluation, ctx, {"s0": "yes", "s1": "yes", "s2": "yes"}, client_request_id="r1")

    result = gates.evaluate(ctx, run.run_id, gate.id)
    assert result.status == "failed"
    assert result.passed is False
    assert result.rules[0].passed is False
    assert ">=" in result.rules[0].expected
    assert result.rules[0].evidence_ref

    read = gates.read_gate(ctx, "suite-1", run.run_id)
    assert read is not None and read.status == "failed"


def test_gate_insufficient_samples_is_not_passed(gates: GateService, ctx, evaluation: EvaluationService) -> None:
    gate = gates.create_gate(ctx, "suite-1", "volume")
    gates.add_rule(ctx, gate.id, name="at least ten", kind="min_samples", min_samples=10)
    run = _run(evaluation, ctx, {"s0": "yes", "s1": "yes"}, client_request_id="r1", sample_count=2)

    result = gates.evaluate(ctx, run.run_id, gate.id)
    assert result.status == "insufficient_data"
    assert result.passed is False
    assert result.rules[0].actual == "2 samples"


def test_gate_relative_baseline(gates: GateService, ctx, evaluation: EvaluationService) -> None:
    baseline = _run(
        evaluation,
        ctx,
        {"s0": "yes", "s1": "yes", "s2": "yes"},
        client_request_id="baseline",
    )
    candidate = _run(
        evaluation,
        ctx,
        {"s0": "no", "s1": "no", "s2": "no"},
        client_request_id="candidate",
    )
    gate = gates.create_gate(ctx, "suite-1", "regression", baseline_run_id=baseline.run_id)
    gates.add_rule(
        ctx,
        gate.id,
        name="no large regression",
        kind="relative",
        metric="accuracy",
        operator="gte",
        threshold=-5.0,
    )
    result = gates.evaluate(ctx, candidate.run_id, gate.id)
    assert result.status == "failed"
    assert result.rules[0].passed is False
    assert "delta=-100" in result.rules[0].actual
    assert baseline.run_id in (result.rules[0].evidence_ref or "")


def test_gate_significance_requires_comparison_data(gates: GateService, ctx, evaluation: EvaluationService) -> None:
    baseline = _run(
        evaluation,
        ctx,
        {f"s{index}": "yes" for index in range(4)},
        client_request_id="baseline",
        sample_count=4,
    )
    candidate = _run(
        evaluation,
        ctx,
        {f"s{index}": "no" for index in range(4)},
        client_request_id="candidate",
        sample_count=4,
    )
    gate = gates.create_gate(ctx, "suite-1", "stats", baseline_run_id=baseline.run_id)
    gates.add_rule(
        ctx,
        gate.id,
        name="significant regression",
        kind="significance",
        metric="accuracy",
        operator="gte",
        threshold=-5.0,
    )
    result = gates.evaluate(ctx, candidate.run_id, gate.id)
    assert result.status == "failed"
    assert result.rules[0].passed is False
    assert "significant=True" in result.rules[0].actual


def test_gate_rejects_manifest_mismatch_and_incomplete_run(
    gates: GateService, ctx, evaluation: EvaluationService
) -> None:
    gate = gates.create_gate(ctx, "suite-1", "quality")
    gates.add_rule(ctx, gate.id, name="accuracy floor", kind="absolute", metric="accuracy", threshold=0.5)
    run = _run(evaluation, ctx, {"s0": "yes", "s1": "yes"}, client_request_id="r1")

    with pytest.raises(InvalidArgumentError):
        gates.evaluate(ctx, run.run_id, gate.id, expected_manifest_hash="b" * 64)

    queued = evaluation.start_run(
        ctx,
        start_request((sample("s0", "yes"),), client_request_id="queued"),
    )
    with pytest.raises(InvalidArgumentError):
        gates.evaluate(ctx, queued.run_id, gate.id)
