"""Retry and circuit-breaker policies for model calls."""

from __future__ import annotations

import random
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from app.core.errors import UpstreamUnavailableError


class SleepFunc(Protocol):
    def __call__(self, seconds: float) -> None: ...


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 3
    base_delay_seconds: float = 0.5
    cap_delay_seconds: float = 10.0
    jitter_ratio: float = 0.1

    def delay(self, attempt: int) -> float:
        delay = min(self.cap_delay_seconds, self.base_delay_seconds * (2**attempt))
        return delay + random.uniform(-delay * self.jitter_ratio, delay * self.jitter_ratio)


class CircuitBreaker:
    def __init__(
        self,
        *,
        failure_threshold: int = 3,
        recovery_seconds: float = 30.0,
        clock: Callable[[], float] | None = None,
    ) -> None:
        if failure_threshold < 1:
            raise ValueError("failure_threshold must be >= 1")
        self._threshold = failure_threshold
        self._recovery = recovery_seconds
        self._clock = clock or time.monotonic
        self._failures = 0
        self._open_until = 0.0
        self._half_open = False

    @property
    def state(self) -> str:
        if self._open_until and self._clock() < self._open_until:
            return "open"
        if self._half_open:
            return "half_open"
        return "closed"

    def before_call(self) -> None:
        if self.state == "open":
            raise UpstreamUnavailableError("provider circuit is open")
        if self._open_until and self._clock() >= self._open_until:
            self._half_open = True

    def record_success(self) -> None:
        self._failures = 0
        self._open_until = 0.0
        self._half_open = False

    def record_failure(self) -> None:
        self._failures += 1
        if self._half_open or self._failures >= self._threshold:
            self._open_until = self._clock() + self._recovery
            self._half_open = False
