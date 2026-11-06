"""Thread-safe gate pass-rate counters (GAT-06).

Operators need to see how often a gate blocks a run, not only the current
result. The counters are process-local and intentionally cheap: every gate
evaluation records exactly one terminal status.
"""

from __future__ import annotations

import threading
from typing import Any

from prometheus_client import Counter, Gauge

_TERMINAL_STATUSES = ("passed", "failed", "insufficient_data")

GATE_RESULTS = Counter("gate_results_total", "Gate evaluation results", ["status"])
GATE_PASS_RATE = Gauge("gate_pass_rate", "Ratio of passing gate evaluations")


class GateMetrics:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counts = {"evaluated": 0, "passed": 0, "failed": 0, "insufficient_data": 0}

    @property
    def evaluated(self) -> int:
        with self._lock:
            return self._counts["evaluated"]

    @property
    def passed(self) -> int:
        with self._lock:
            return self._counts["passed"]

    @property
    def failed(self) -> int:
        with self._lock:
            return self._counts["failed"]

    @property
    def insufficient_data(self) -> int:
        with self._lock:
            return self._counts["insufficient_data"]

    @property
    def pass_rate(self) -> float:
        with self._lock:
            evaluated = self._counts["evaluated"]
            return self._counts["passed"] / evaluated if evaluated else 0.0

    def record(self, status: str) -> None:
        """Record one terminal gate status exactly once."""

        if status not in _TERMINAL_STATUSES:
            raise ValueError(f"unsupported gate status: {status}")
        with self._lock:
            self._counts["evaluated"] += 1
            self._counts[status] += 1
            GATE_RESULTS.labels(status=status).inc()
            GATE_PASS_RATE.set(self._counts["passed"] / self._counts["evaluated"] if self._counts["evaluated"] else 0.0)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            evaluated = self._counts["evaluated"]
            return {
                "evaluated": evaluated,
                "passed": self._counts["passed"],
                "failed": self._counts["failed"],
                "insufficient_data": self._counts["insufficient_data"],
                "pass_rate": self._counts["passed"] / evaluated if evaluated else 0.0,
            }

    def reset(self) -> None:
        with self._lock:
            for key in self._counts:
                self._counts[key] = 0
