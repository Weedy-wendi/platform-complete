"""Gate rule matrix: pass, fail, missing data, sample size (GAT-02)."""

from __future__ import annotations

import pytest

from app.core.errors import InvalidArgumentError
from app.modules.evaluation.public import MetricComparison, MetricSummary
from app.modules.gate.rules import RuleSpec, compare_actual, evaluate_rule, validate_rule


def _candidate(value: float, count: int = 5) -> MetricSummary:
    return MetricSummary("accuracy", value, count=count, stdev=0.0, direction="higher_is_better")


def _evaluate(spec: RuleSpec, *, candidate=None, baseline=None, comparison=None, baseline_run_id=None):
    return evaluate_rule(
        spec,
        run_id="run-1",
        candidate=candidate,
        baseline=baseline,
        comparison=comparison,
        baseline_run_id=baseline_run_id,
        succeeded_items=5,
    )


def test_absolute_rule_pass_and_fail() -> None:
    spec = RuleSpec("accuracy floor", "absolute", metric="accuracy", operator="gte", threshold=0.8)
    result, insufficient = _evaluate(spec, candidate=_candidate(0.9))
    assert result.passed is True
    assert insufficient is False
    assert "0.9" in result.actual
    assert result.evidence_ref and "run-1" in result.evidence_ref

    result, insufficient = _evaluate(spec, candidate=_candidate(0.5))
    assert result.passed is False
    assert insufficient is False


def test_absolute_rule_operators() -> None:
    assert compare_actual(1.0, "gte", 1.0)
    assert compare_actual(1.0, "lte", 1.0)
    assert compare_actual(2.0, "gt", 1.0)
    assert compare_actual(0.5, "lt", 1.0)
    assert compare_actual(1.0, "eq", 1.0)
    with pytest.raises(InvalidArgumentError):
        compare_actual(1.0, "between", 1.0)


def test_missing_metric_is_insufficient_data() -> None:
    spec = RuleSpec("accuracy floor", "absolute", metric="accuracy", threshold=0.8)
    result, insufficient = _evaluate(spec)
    assert result.passed is False
    assert insufficient is True
    assert result.actual == "metric missing"


def test_min_samples_rule() -> None:
    spec = RuleSpec("enough data", "min_samples", min_samples=10)
    result, insufficient = _evaluate(spec, candidate=_candidate(1.0, count=4))
    assert result.passed is False
    assert insufficient is True
    assert result.actual == "4 samples"

    result, insufficient = _evaluate(spec, candidate=_candidate(1.0, count=12))
    assert result.passed is True
    assert insufficient is False


def test_relative_rule_uses_baseline() -> None:
    baseline = _candidate(1.0)
    spec = RuleSpec(
        "no regression",
        "relative",
        metric="accuracy",
        operator="gte",
        threshold=-5.0,
    )
    result, insufficient = _evaluate(spec, candidate=_candidate(0.5), baseline=baseline, baseline_run_id="run-0")
    assert result.passed is False
    assert insufficient is False
    assert "delta=-50" in result.actual
    assert result.evidence_ref and "run-0" in result.evidence_ref

    result, insufficient = _evaluate(spec, candidate=_candidate(1.0), baseline=None)
    assert insufficient is True


def test_significance_rule_requires_samples_and_effect() -> None:
    comparison = MetricComparison(
        name="accuracy",
        baseline=1.0,
        candidate=0.8,
        delta=-0.2,
        delta_pct=-20.0,
        direction="higher_is_better",
        significant=True,
        ci_low=-0.3,
        ci_high=-0.1,
        baseline_n=10,
        candidate_n=10,
    )
    spec = RuleSpec("significant regression", "significance", metric="accuracy", operator="gte", threshold=-5.0)
    result, insufficient = _evaluate(spec, candidate=_candidate(0.8), comparison=comparison)
    assert result.passed is False
    assert insufficient is False
    assert "ci=" in result.actual

    low_sample = MetricComparison(
        name="accuracy",
        baseline=1.0,
        candidate=0.8,
        delta=-0.2,
        delta_pct=-20.0,
        direction="higher_is_better",
        significant=False,
        baseline_n=1,
        candidate_n=1,
    )
    result, insufficient = _evaluate(spec, candidate=_candidate(0.8), comparison=low_sample)
    assert result.passed is False
    assert insufficient is True


def test_rule_validation() -> None:
    with pytest.raises(InvalidArgumentError):
        validate_rule(RuleSpec("", "absolute", metric="accuracy"))
    with pytest.raises(InvalidArgumentError):
        validate_rule(RuleSpec("x", "nope", metric="accuracy"))
    with pytest.raises(InvalidArgumentError):
        validate_rule(RuleSpec("x", "absolute", metric=""))
    with pytest.raises(InvalidArgumentError):
        validate_rule(RuleSpec("x", "min_samples", min_samples=0))
