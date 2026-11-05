"""Kill-switch tests (QUAL-04)."""

from __future__ import annotations

import pytest

from app.core.errors import ServiceUnavailableError
from app.core.kill_switch import KILL_SWITCHES, KillSwitchRegistry


def test_default_switches_exist() -> None:
    assert {"models", "evaluation", "mcp"} <= set(KILL_SWITCHES.snapshot())


def test_switch_disables_and_recovers() -> None:
    registry = KillSwitchRegistry()
    registry.register("models")
    registry.require("models")
    registry.set("models", True, reason="provider incident")
    with pytest.raises(ServiceUnavailableError):
        registry.require("models")
    assert registry.snapshot()["models"]["enabled"] is True
    registry.set("models", False)
    registry.require("models")
