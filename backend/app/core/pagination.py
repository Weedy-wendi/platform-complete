"""Pagination primitives."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Page[T]:
    items: list[T] = field(default_factory=list)
    next_cursor: str | None = None
    truncated: bool = False


def clamp_limit(limit: int | None, *, default: int = 20, maximum: int = 100) -> int:
    if limit is None:
        return default
    if limit < 1:
        raise ValueError("limit must be >= 1")
    return min(limit, maximum)
