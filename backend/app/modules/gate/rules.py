"""Gate rule evaluation.

Every decision is explainable: expected, actual and an evidence reference are
returned even when a rule cannot be evaluated because data is missing.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from app.core.errors import InvalidArgumentError
from app.modules.evaluation.public import MetricComparison, MetricSummary

RULE_KINDS = {"absolute", "relative", "significance", "min_samples"}
OPERATORS = {"gte": ">=", "lte": "<=", "gt": ">", "lt": "<", "eq": "=="}

_COMPARATORS: dict[str, Callable[[float, float], bool]] = {
    "gte": lambda actual, threshold: actual >= threshold,
    "lte": lambda actual, threshold: actual <= threshold,
    "gt": lambda actual, threshold: actual > threshold,
    "lt": lambda actual, threshold: actual < threshold,
    "eq": lambda actual, threshold: actual == threshold,
}


@dataclass(frozen=True)
class GateRule:
    name: str
    kind: str
    expected: str
    actual: str
    passed: bool
    evidence_ref: str | None = None


@dataclass(frozen=True)
class RuleSpec:
    name: str
    kind: str
    metric: str = ""
    operator: str = "gte"
    threshold: float = 0.0
    baseline_run_id: str | None = None
    min_samples: int | None = None


def validate_rule(spec: RuleSpec) -> None:
    if not spec.name.strip():
        raise InvalidArgumentError("gate rule name is required")
    if spec.kind not in RULE_KINDS:
        raise InvalidArgumentError("unknown gate rule kind", kind=spec.kind)
    if spec.operator not in OPERATORS:
        raise InvalidArgumentError("unknown gate rule operator", operator=spec.operator)
    if spec.kind != "min_samples" and not spec.metric.strip():
        raise InvalidArgumentError("gate rule metric is required")
    if spec.kind == "min_samples" and (spec.min_samples is None or spec.min_samples < 1):
        raise InvalidArgumentError("min_samples must be at least 1")


def compare_actual(actual: float, operator: str, threshold: float) -> bool:
    comparator = _COMPARATORS.get(operator)
    if comparator is None:
        raise InvalidArgumentError("unknown gate rule operator", operator=operator)
    return comparator(actual, threshold)


def _evidence(run_id: str, metric: str, *, baseline_run_id: str | None = None) -> str:
    suffix = f"#metric={metric}" if metric else ""
    if baseline_run_id:
        return f"evaluation://runs/{run_id}/compare/{baseline_run_id}{suffix}"
    return f"evaluation://runs/{run_id}/items{suffix}"


def evaluate_rule(
    spec: RuleSpec,
    *,
    run_id: str,
    candidate: MetricSummary | None,
    baseline: MetricSummary | None,
    comparison: MetricComparison | None,
    baseline_run_id: str | None,
    succeeded_items: int,
) -> tuple[GateRule, bool]:
    """Return the rule result and whether it was ``insufficient_data``."""

    validate_rule(spec)
    symbol = OPERATORS[spec.operator]
    evidence = _evidence(run_id, spec.metric, baseline_run_id=baseline_run_id)

    if spec.kind == "min_samples":
        minimum = int(spec.min_samples or 1)
        actual_count = candidate.count if candidate is not None else succeeded_items
        passed = actual_count >= minimum
        return (
            GateRule(
                name=spec.name,
                kind=spec.kind,
                expected=f">= {minimum} samples",
                actual=f"{actual_count} samples",
                passed=passed,
                evidence_ref=evidence,
            ),
            not passed,
        )

    if candidate is None:
        return (
            GateRule(
                name=spec.name,
                kind=spec.kind,
                expected=f"{symbol} {spec.threshold}",
                actual="metric missing",
                passed=False,
                evidence_ref=evidence,
            ),
            True,
        )

    if spec.kind == "absolute":
        passed = compare_actual(candidate.value, spec.operator, spec.threshold)
        return (
            GateRule(
                name=spec.name,
                kind=spec.kind,
                expected=f"{spec.metric} {symbol} {spec.threshold}",
                actual=f"{spec.metric}={candidate.value:.6f}",
                passed=passed,
                evidence_ref=evidence,
            ),
            False,
        )

    if spec.kind == "relative":
        if baseline is None or baseline.value == 0:
            return (
                GateRule(
                    name=spec.name,
                    kind=spec.kind,
                    expected=f"{symbol} {spec.threshold}% vs baseline",
                    actual="baseline missing or zero",
                    passed=False,
                    evidence_ref=evidence,
                ),
                True,
            )
        delta_pct = (candidate.value - baseline.value) / abs(baseline.value) * 100.0
        passed = compare_actual(delta_pct, spec.operator, spec.threshold)
        return (
            GateRule(
                name=spec.name,
                kind=spec.kind,
                expected=f"{spec.metric} {symbol} {spec.threshold}% vs baseline",
                actual=f"delta={delta_pct:.4f}% (baseline={baseline.value:.6f}, candidate={candidate.value:.6f})",
                passed=passed,
                evidence_ref=evidence,
            ),
            False,
        )

    # significance
    if comparison is None or comparison.baseline_n < 2 or comparison.candidate_n < 2:
        return (
            GateRule(
                name=spec.name,
                kind=spec.kind,
                expected=f"statistically significant change {symbol} {spec.threshold}%",
                actual="insufficient samples or comparison unavailable",
                passed=False,
                evidence_ref=evidence,
            ),
            True,
        )
    passed = comparison.significant and compare_actual(comparison.delta_pct, spec.operator, spec.threshold)
    interval = (
        f"ci=[{comparison.ci_low:.6f}, {comparison.ci_high:.6f}]"
        if comparison.ci_low is not None and comparison.ci_high is not None
        else "ci=unavailable"
    )
    return (
        GateRule(
            name=spec.name,
            kind=spec.kind,
            expected=f"significant delta {symbol} {spec.threshold}%",
            actual=f"delta={comparison.delta_pct:.4f}% significant={comparison.significant} {interval}",
            passed=passed,
            evidence_ref=evidence,
        ),
        False,
    )
