"""Retry policy for jobs."""

from __future__ import annotations

import random
from typing import Protocol


class RandomSource(Protocol):
    def uniform(self, a: float, b: float) -> float: ...


def backoff_delay(
    attempt: int,
    *,
    base_seconds: float = 1.0,
    cap_seconds: float = 60.0,
    jitter_ratio: float = 0.2,
    rng: RandomSource | None = None,
) -> float:
    if attempt < 0:
        raise ValueError("attempt must be >= 0")
    if base_seconds <= 0 or cap_seconds <= 0:
        raise ValueError("base_seconds and cap_seconds must be positive")
    if not 0 <= jitter_ratio < 1:
        raise ValueError("jitter_ratio must be in [0, 1)")
    source = rng or random
    delay = min(cap_seconds, base_seconds * (2**attempt))
    return delay + source.uniform(-delay * jitter_ratio, delay * jitter_ratio)
