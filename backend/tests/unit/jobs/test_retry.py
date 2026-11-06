"""Retry and Celery configuration tests (JOB-02/03)."""

from __future__ import annotations

from app.modules.jobs.retry import backoff_delay
from app.modules.jobs.runner import CELERY_CONFIG


class FixedRandom:
    def uniform(self, a: float, b: float) -> float:
        return 0.0


def test_backoff_is_exponential_and_capped() -> None:
    rng = FixedRandom()
    assert backoff_delay(0, rng=rng) == 1.0
    assert backoff_delay(1, rng=rng) == 2.0
    assert backoff_delay(2, rng=rng) == 4.0
    assert backoff_delay(10, cap_seconds=60, rng=rng) == 60.0


def test_backoff_rejects_invalid_inputs() -> None:
    import pytest

    with pytest.raises(ValueError):
        backoff_delay(-1)
    with pytest.raises(ValueError):
        backoff_delay(0, jitter_ratio=1.0)


def test_celery_safety_config() -> None:
    assert CELERY_CONFIG["task_acks_late"] is True
    assert CELERY_CONFIG["task_reject_on_worker_lost"] is True
    assert CELERY_CONFIG["worker_prefetch_multiplier"] == 1
    assert CELERY_CONFIG["broker_transport_options"]["visibility_timeout"] == 21600
