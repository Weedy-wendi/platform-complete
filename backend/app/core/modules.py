"""Module discovery helpers.

The module map is the source of truth for boundaries. This helper enumerates the
installed business modules without importing them, which keeps startup checks
cheap and avoids import cycles.
"""

from __future__ import annotations

from pathlib import Path


def list_modules() -> tuple[str, ...]:
    """Return the business module names currently present on disk."""
    modules_dir = Path(__file__).resolve().parents[1] / "modules"
    if not modules_dir.exists():
        return ()
    return tuple(
        sorted(
            path.name
            for path in modules_dir.iterdir()
            if path.is_dir() and (path / "__init__.py").exists() and not path.name.startswith("_")
        )
    )
