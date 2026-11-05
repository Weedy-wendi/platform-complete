"""Evaluation read service."""

from __future__ import annotations

from dataclasses import dataclass

from app.core.errors import NotFoundError
from app.services.models import Evaluator, MetricDirection, Run, RunItem
from app.services.repositories import EvaluatorRepository, RunRepository

SIGNIFICANCE_THRESHOLD_PCT = 5.0


@dataclass(frozen=True)
class MetricComparison:
    name: str
    baseline: float
    candidate: float
    delta: float
    delta_pct: float
    significant: bool
    direction: MetricDirection


@dataclass(frozen=True)
class Comparison:
    metrics: list[MetricComparison]
    regressions: list[MetricComparison]
    improvements: list[MetricComparison]
    warnings: list[str]


class EvaluationService:
    def __init__(self, evaluators: EvaluatorRepository, runs: RunRepository) -> None:
        self._evaluators = evaluators
        self._runs = runs

    def list_evaluators(self, tenant_id: str, project_id: str | None = None) -> list[Evaluator]:
        return [
            evaluator
            for evaluator in self._evaluators.list_for_tenant(tenant_id, project_id)
            if evaluator.tenant_id == tenant_id and evaluator.published
        ]

    def get_run(self, tenant_id: str, run_id: str) -> Run:
        run = self._runs.get(tenant_id, run_id)
        if run is None or run.tenant_id != tenant_id:
            # Do not disclose whether the run exists in another tenant.
            raise NotFoundError("Run not found", run_id=run_id)
        return run

    def list_items(self, tenant_id: str, run_id: str) -> list[RunItem]:
        self.get_run(tenant_id, run_id)
        return [item for item in self._runs.list_items(tenant_id, run_id) if item.tenant_id == tenant_id]

    def compare_runs(
        self,
        tenant_id: str,
        run_id_a: str,
        run_id_b: str,
        metric_names: list[str] | None = None,
    ) -> Comparison:
        baseline = self.get_run(tenant_id, run_id_a)
        candidate = self.get_run(tenant_id, run_id_b)
        warnings: list[str] = []
        if baseline.suite_id != candidate.suite_id:
            warnings.append("runs use different suites")
        if (baseline.dataset_id, baseline.dataset_version) != (candidate.dataset_id, candidate.dataset_version):
            warnings.append("runs use different dataset versions")
        if baseline.manifest_hash == candidate.manifest_hash:
            warnings.append("runs share the same manifest hash")

        baseline_metrics = {metric.name: metric for metric in baseline.metrics}
        candidate_metrics = {metric.name: metric for metric in candidate.metrics}
        selected = metric_names or sorted(set(baseline_metrics) & set(candidate_metrics))
        comparisons: list[MetricComparison] = []
        for name in selected:
            left = baseline_metrics.get(name)
            right = candidate_metrics.get(name)
            if left is None or right is None:
                warnings.append(f"metric not available in both runs: {name}")
                continue
            delta = right.value - left.value
            delta_pct = (delta / abs(left.value) * 100.0) if left.value != 0 else 0.0
            comparisons.append(
                MetricComparison(
                    name=name,
                    baseline=left.value,
                    candidate=right.value,
                    delta=delta,
                    delta_pct=delta_pct,
                    significant=abs(delta_pct) >= SIGNIFICANCE_THRESHOLD_PCT,
                    direction=left.direction,
                )
            )

        regressions = [item for item in comparisons if _is_regression(item.direction, item.delta) and item.delta != 0]
        improvements = [
            item for item in comparisons if not _is_regression(item.direction, item.delta) and item.delta != 0
        ]
        return Comparison(
            metrics=comparisons,
            regressions=regressions,
            improvements=improvements,
            warnings=warnings,
        )


def _is_regression(direction: MetricDirection, delta: float) -> bool:
    if direction == "lower_is_better":
        return delta > 0
    return delta < 0
