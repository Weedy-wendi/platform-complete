"""Gate reader boundary.

`check_gate` must delegate to the platform's gate service (GAT-04). The MCP
layer must not evaluate gate rules itself.
"""

from __future__ import annotations

from typing import Protocol

from app.core.errors import UpstreamUnavailableError
from app.services.models import GateResult


class GateReader(Protocol):
    def read_gate(self, *, tenant_id: str, suite_id: str, run_id: str) -> GateResult | None: ...


class UnavailableGateReader:
    """Dependency placeholder used until GAT-04 is deployed."""

    def read_gate(self, *, tenant_id: str, suite_id: str, run_id: str) -> GateResult | None:
        raise UpstreamUnavailableError("Gate service is not available")
