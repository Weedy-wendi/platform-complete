"""Module enumeration tests (CORE-01)."""

from __future__ import annotations

from app.core.modules import list_modules


def test_list_modules_is_sorted_and_contains_known_modules() -> None:
    modules = list_modules()
    assert "audit" in modules
    assert "identity" in modules
    assert modules == tuple(sorted(modules))
