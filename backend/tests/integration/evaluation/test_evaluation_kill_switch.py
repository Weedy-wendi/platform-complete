"""Evaluation kill switch wiring (QUAL-08)."""

from __future__ import annotations

import pytest

from app.core.errors import ServiceUnavailableError
from app.core.kill_switch import KILL_SWITCHES
from tests.integration.evaluation.support import sample, start_request


def test_evaluation_kill_switch_blocks_new_runs(service, ctx) -> None:
    KILL_SWITCHES.set("evaluation", True, reason="test")
    try:
        with pytest.raises(ServiceUnavailableError):
            service.start_run(ctx, start_request((sample("s1", "yes"),)))
    finally:
        KILL_SWITCHES.set("evaluation", False)
