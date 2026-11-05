"""Judge calibration and Cohen's kappa (EVL-17)."""

from __future__ import annotations

import pytest

from app.core.errors import InvalidArgumentError
from app.modules.evaluation.public import (
    CalibrationReport,
    calibration_report,
    cohen_kappa,
    require_calibrated,
)


def test_perfect_agreement_is_one() -> None:
    labels = ["pass", "fail", "pass", "fail", "pass"]
    assert cohen_kappa(labels, labels) == pytest.approx(1.0)
    report = calibration_report(labels, labels)
    assert report.kappa == pytest.approx(1.0)
    assert report.observed_agreement == pytest.approx(1.0)
    assert report.sample_size == 5
    assert report.labels == ("fail", "pass")


def test_systematic_disagreement_is_negative() -> None:
    kappa = cohen_kappa(["pass", "pass", "fail", "fail"], ["fail", "fail", "pass", "pass"])
    assert kappa < 0.0
    assert kappa == pytest.approx(-1.0)


def test_chance_level_is_near_zero() -> None:
    labels_a = ["a", "a", "b", "b", "a", "a", "b", "b"]
    labels_b = ["a", "b", "a", "b", "a", "b", "a", "b"]
    assert cohen_kappa(labels_a, labels_b) == pytest.approx(0.0, abs=0.05)


def test_binary_and_categorical_labels_are_supported() -> None:
    binary = cohen_kappa([True, False, True, False], [True, False, True, True])
    assert binary == pytest.approx(0.4667, abs=0.001)
    report = calibration_report(["good", "bad", "ok", "good"], ["good", "bad", "ok", "bad"])
    assert report.labels == ("bad", "good", "ok")
    assert report.sample_size == 4


@pytest.mark.parametrize(
    ("labels_a", "labels_b"),
    [
        ([], []),
        (["a"], ["a", "b"]),
        (["a", "b"], ["a"]),
    ],
)
def test_invalid_label_sets_raise(labels_a: list[str], labels_b: list[str]) -> None:
    with pytest.raises(InvalidArgumentError):
        cohen_kappa(labels_a, labels_b)
    with pytest.raises(InvalidArgumentError):
        calibration_report(labels_a, labels_b)


def test_threshold_gate_rejects_below_and_accepts_at_or_above() -> None:
    below = CalibrationReport(kappa=0.69, observed_agreement=0.8, sample_size=20, labels=("a", "b"))
    with pytest.raises(InvalidArgumentError) as exc_info:
        require_calibrated(below)
    assert exc_info.value.details["kappa"] == pytest.approx(0.69)
    assert below.is_usable() is False

    at_threshold = CalibrationReport(kappa=0.7, observed_agreement=0.8, sample_size=20, labels=("a", "b"))
    assert at_threshold.is_usable() is True
    require_calibrated(at_threshold)

    require_calibrated(below, threshold=0.6)
