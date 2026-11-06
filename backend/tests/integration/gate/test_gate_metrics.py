"""Gate evaluation counts terminal statuses exactly once (GAT-06)."""

from __future__ import annotations

import pytest

from app.modules.evaluation.service import EvaluationService
from app.modules.evaluation.types import RunView
from app.modules.gate.public import GateService
from tests.integration.evaluation.support import FakeAdapter, sample, start_request


def _run(evaluation: EvaluationService, ctx) -> RunView:
    samples = tuple(sample(f"s{index}", "yes") for index in range(3))
    run = evaluation.start_run(ctx, start_request(samples, client_request_id="metrics-run"))
    return evaluation.execute(ctx, run.run_id, adapter=FakeAdapter({"s0": "yes", "s1": "yes", "s2": "yes"}))


def test_gate_metrics_count_allow_deny_and_insufficient(gates: GateService, ctx, evaluation: EvaluationService) -> None:
    run = _run(evaluation, ctx)

    allowed = gates.create_gate(ctx, "suite-1", "allow")
    gates.add_rule(ctx, allowed.id, name="accuracy floor", kind="absolute", metric="accuracy", threshold=0.9)
    assert gates.evaluate(ctx, run.run_id, allowed.id).status == "passed"

    denied = gates.create_gate(ctx, "suite-1", "deny")
    gates.add_rule(ctx, denied.id, name="impossible floor", kind="absolute", metric="accuracy", threshold=1.1)
    assert gates.evaluate(ctx, run.run_id, denied.id).status == "failed"

    insufficient = gates.create_gate(ctx, "suite-1", "volume")
    gates.add_rule(ctx, insufficient.id, name="at least ten", kind="min_samples", min_samples=10)
    assert gates.evaluate(ctx, run.run_id, insufficient.id).status == "insufficient_data"

    snapshot = gates.metrics.snapshot()
    assert snapshot["evaluated"] == 3
    assert snapshot["passed"] == 1
    assert snapshot["failed"] == 1
    assert snapshot["insufficient_data"] == 1
    assert snapshot["pass_rate"] == pytest.approx(1 / 3)
    assert gates.metrics.evaluated == 3
    assert gates.metrics.pass_rate == pytest.approx(1 / 3)
