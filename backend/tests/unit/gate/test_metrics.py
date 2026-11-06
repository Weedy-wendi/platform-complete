"""Thread-safe gate pass-rate counters (GAT-06)."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pytest

from app.modules.gate.public import GateMetrics


def test_initial_snapshot_and_reset() -> None:
    metrics = GateMetrics()
    assert metrics.snapshot() == {
        "evaluated": 0,
        "passed": 0,
        "failed": 0,
        "insufficient_data": 0,
        "pass_rate": 0.0,
    }
    assert metrics.pass_rate == 0.0

    metrics.record("passed")
    metrics.record("failed")
    metrics.record("insufficient_data")
    snapshot = metrics.snapshot()
    assert snapshot["evaluated"] == 3
    assert snapshot["passed"] == 1
    assert snapshot["failed"] == 1
    assert snapshot["insufficient_data"] == 1
    assert snapshot["pass_rate"] == pytest.approx(1 / 3)

    metrics.reset()
    assert metrics.evaluated == 0
    assert metrics.pass_rate == 0.0


def test_pass_rate_and_counters() -> None:
    metrics = GateMetrics()
    for status in ["passed", "passed", "passed", "failed"]:
        metrics.record(status)
    assert metrics.evaluated == 4
    assert metrics.passed == 3
    assert metrics.failed == 1
    assert metrics.insufficient_data == 0
    assert metrics.pass_rate == pytest.approx(0.75)


def test_counters_are_thread_safe() -> None:
    metrics = GateMetrics()

    def record(status: str) -> None:
        for _ in range(250):
            metrics.record(status)

    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = [
            executor.submit(record, "passed"),
            executor.submit(record, "failed"),
            executor.submit(record, "insufficient_data"),
            executor.submit(record, "passed"),
        ]
        for future in futures:
            future.result()

    snapshot = metrics.snapshot()
    assert snapshot["evaluated"] == 1000
    assert snapshot["passed"] == 500
    assert snapshot["failed"] == 250
    assert snapshot["insufficient_data"] == 250
    assert snapshot["pass_rate"] == pytest.approx(0.5)


def test_unknown_status_is_rejected() -> None:
    metrics = GateMetrics()
    with pytest.raises(ValueError):
        metrics.record("unknown")
    assert metrics.evaluated == 0


def test_prometheus_gauge_tracks_pass_rate() -> None:
    from prometheus_client import REGISTRY

    metrics = GateMetrics()
    metrics.record("passed")
    metrics.record("failed")
    assert REGISTRY.get_sample_value("gate_pass_rate") == pytest.approx(metrics.pass_rate)
    assert REGISTRY.get_sample_value("gate_results_total", {"status": "passed"}) >= 1
