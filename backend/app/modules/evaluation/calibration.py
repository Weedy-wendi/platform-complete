"""Judge calibration via Cohen's kappa (EVL-17).

A judge is only trustworthy enough to gate a release when its labels agree
with a human review set substantially better than chance. The report is a
frozen snapshot so calibration evidence cannot be edited after the fact.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from app.core.errors import InvalidArgumentError


def cohen_kappa(labels_a: Sequence[Any], labels_b: Sequence[Any]) -> float:
    """Return Cohen's kappa for two equally sized label sequences.

    Works for both binary and categorical labels. Labels are compared by their
    string form so callers may pass strings, booleans or integers while the
    public label inventory stays a stable tuple of strings.
    """

    if len(labels_a) != len(labels_b):
        raise InvalidArgumentError(
            "label sets must have the same length",
            labels_a=len(labels_a),
            labels_b=len(labels_b),
        )
    if not labels_a:
        raise InvalidArgumentError("at least one label pair is required")

    first = [str(label) for label in labels_a]
    second = [str(label) for label in labels_b]
    sample_size = len(first)
    observed_agreement = sum(left == right for left, right in zip(first, second, strict=True)) / sample_size

    counts_a = Counter(first)
    counts_b = Counter(second)
    categories = set(counts_a) | set(counts_b)
    expected_agreement = sum(
        ((counts_a[category] + counts_b[category]) / (2 * sample_size)) ** 2 for category in categories
    )

    if expected_agreement >= 1.0:
        # Degenerate case: every label is identical, so chance agreement is 1.
        return 1.0 if observed_agreement >= 1.0 else 0.0
    return (observed_agreement - expected_agreement) / (1.0 - expected_agreement)


@dataclass(frozen=True)
class CalibrationReport:
    kappa: float
    observed_agreement: float
    sample_size: int
    labels: tuple[str, ...]

    def is_usable(self, threshold: float = 0.7) -> bool:
        return self.kappa >= threshold


def calibration_report(labels_a: Sequence[Any], labels_b: Sequence[Any]) -> CalibrationReport:
    if len(labels_a) != len(labels_b):
        raise InvalidArgumentError(
            "label sets must have the same length",
            labels_a=len(labels_a),
            labels_b=len(labels_b),
        )
    if not labels_a:
        raise InvalidArgumentError("at least one label pair is required")
    observed = sum(str(left) == str(right) for left, right in zip(labels_a, labels_b, strict=True)) / len(labels_a)
    labels = tuple(sorted({str(label) for label in labels_a} | {str(label) for label in labels_b}))
    return CalibrationReport(
        kappa=cohen_kappa(labels_a, labels_b),
        observed_agreement=observed,
        sample_size=len(labels_a),
        labels=labels,
    )


def require_calibrated(report: CalibrationReport, threshold: float = 0.7) -> None:
    """Reject judge labels that do not clear the calibration threshold."""

    if not report.is_usable(threshold):
        raise InvalidArgumentError(
            "judge calibration is below the required threshold",
            kappa=report.kappa,
            threshold=threshold,
            observed_agreement=report.observed_agreement,
            sample_size=report.sample_size,
        )
