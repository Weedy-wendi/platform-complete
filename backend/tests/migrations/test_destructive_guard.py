"""Migration guard: destructive DDL must be explicitly approved (QUAL-03)."""

from __future__ import annotations

import ast
from pathlib import Path

VERSIONS = Path(__file__).resolve().parents[2] / "migrations" / "versions"
_DESTRUCTIVE = ("drop_table", "drop_column", "drop_constraint", "DROP TABLE", "DROP COLUMN")


def _upgrade_source(path: Path) -> str:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "upgrade":
            return ast.get_source_segment(source, node) or ""
    return ""


def test_destructive_upgrade_requires_approval() -> None:
    violations: list[str] = []
    for path in sorted(VERSIONS.glob("*.py")):
        source = _upgrade_source(path)
        if "destructive-approved" in source:
            continue
        for marker in _DESTRUCTIVE:
            if marker in source:
                violations.append(f"{path.name}: {marker}")
    assert not violations, "destructive DDL without approval:\n" + "\n".join(violations)
