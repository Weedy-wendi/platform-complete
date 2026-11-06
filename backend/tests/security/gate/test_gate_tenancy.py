"""Cross-tenant gates and results are not visible (011 invariant 5)."""

from __future__ import annotations

import pytest

from app.core.errors import NotFoundError
from app.modules.evaluation.service import EvaluationService
from app.modules.gate.service import GateService
from tests.integration.evaluation.support import FakeAdapter, sample, start_request


def test_cross_tenant_gate_is_not_found(gates: GateService, evaluation: EvaluationService, ctx, other_ctx) -> None:
    gate = gates.create_gate(ctx, "suite-1", "quality")
    gates.add_rule(ctx, gate.id, name="accuracy", kind="absolute", metric="accuracy", threshold=0.5)
    run = evaluation.start_run(ctx, start_request((sample("s1", "yes"),)))
    evaluation.execute(ctx, run.run_id, adapter=FakeAdapter({"s1": "yes"}))

    with pytest.raises(NotFoundError):
        gates.get_gate(other_ctx, gate.id)
    with pytest.raises(NotFoundError):
        gates.add_rule(other_ctx, gate.id, name="other", kind="absolute", metric="accuracy", threshold=0.5)
    with pytest.raises(NotFoundError):
        gates.evaluate(other_ctx, run.run_id, gate.id)
    assert gates.read_gate(other_ctx, "suite-1", run.run_id) is None
    assert gates.read_gate_for_gate(other_ctx, gate.id, run.run_id) is None


def test_cross_tenant_run_cannot_be_evaluated(
    gates: GateService, evaluation: EvaluationService, ctx, other_ctx
) -> None:
    run = evaluation.start_run(ctx, start_request((sample("s1", "yes"),)))
    evaluation.execute(ctx, run.run_id, adapter=FakeAdapter({"s1": "yes"}))
    their_gate = gates.create_gate(other_ctx, "suite-1", "their-quality")
    gates.add_rule(
        other_ctx,
        their_gate.id,
        name="accuracy",
        kind="absolute",
        metric="accuracy",
        threshold=0.5,
    )
    with pytest.raises(NotFoundError):
        gates.evaluate(other_ctx, run.run_id, their_gate.id)


def test_gate_names_are_tenant_scoped(gates: GateService, ctx, other_ctx) -> None:
    mine = gates.create_gate(ctx, "suite-1", "quality")
    theirs = gates.create_gate(other_ctx, "suite-1", "quality")
    assert mine.id != theirs.id
    assert mine.tenant_id == "tenant-a"
    assert theirs.tenant_id == "tenant-b"
