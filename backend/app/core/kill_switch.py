"""Runtime kill switches for model, evaluation and MCP paths."""

from __future__ import annotations

from dataclasses import dataclass

from app.core.errors import ServiceUnavailableError
from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class KillSwitch:
    name: str
    enabled: bool = False
    reason: str = ""


class KillSwitchRegistry:
    def __init__(self) -> None:
        self._switches: dict[str, KillSwitch] = {}

    def register(self, name: str) -> None:
        self._switches.setdefault(name, KillSwitch(name))

    def set(self, name: str, enabled: bool, *, reason: str = "") -> None:
        self.register(name)
        switch = self._switches[name]
        switch.enabled = enabled
        switch.reason = reason
        logger.warning("kill_switch_changed", extra={"switch": name, "enabled": enabled})

    def is_enabled(self, name: str) -> bool:
        self.register(name)
        return self._switches[name].enabled

    def require(self, name: str) -> None:
        if self.is_enabled(name):
            reason = self._switches[name].reason or "disabled by operator"
            raise ServiceUnavailableError(f"{name} is disabled: {reason}")

    def snapshot(self) -> dict[str, dict[str, object]]:
        return {name: {"enabled": switch.enabled, "reason": switch.reason} for name, switch in self._switches.items()}


KILL_SWITCHES = KillSwitchRegistry()

DEFAULT_KILL_SWITCHES = ("models", "evaluation", "mcp")
for _name in DEFAULT_KILL_SWITCHES:
    KILL_SWITCHES.register(_name)
