"""Run budget checks.

Creation rejects an estimate above the budget. Execution pauses instead of
failing so an operator can raise the budget and resume the run.
"""

from __future__ import annotations

from app.core.errors import InvalidArgumentError


def validate_budget(budget_usd: float | None, estimated_cost_usd: float = 0.0) -> None:
    if budget_usd is not None and budget_usd < 0:
        raise InvalidArgumentError("budget_usd must be non-negative")
    if estimated_cost_usd < 0:
        raise InvalidArgumentError("estimated_cost_usd must be non-negative")
    if budget_usd is not None and estimated_cost_usd > budget_usd:
        raise InvalidArgumentError(
            "estimated cost exceeds the run budget",
            budget_usd=budget_usd,
            estimated_cost_usd=estimated_cost_usd,
        )


def is_over_budget(cost_usd: float, budget_usd: float | None) -> bool:
    return budget_usd is not None and cost_usd >= budget_usd
