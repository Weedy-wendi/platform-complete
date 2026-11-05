"""Architecture fitness function: enforce module boundaries."""

from __future__ import annotations

import ast
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[2] / "app"
MODULES_DIR = APP_DIR / "modules"
MCP_DIR = APP_DIR / "mcp"


def _module_owner(path: Path) -> str | None:
    try:
        relative = path.relative_to(MODULES_DIR)
    except ValueError:
        return None
    return relative.parts[0]


def _imported_modules(tree: ast.AST) -> list[str]:
    result: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            result.append(node.module)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                result.append(alias.name)
    return result


def _package_of(module: str) -> str | None:
    parts = module.split(".")
    if len(parts) < 2 or parts[0] != "app":
        return None
    if parts[1] in {"core", "mcp", "services", "api", "cli"}:
        return f"app.{parts[1]}"
    if parts[1] == "modules" and len(parts) >= 3:
        return f"app.modules.{parts[2]}"
    return None


def _source_package(path: Path) -> str | None:
    relative = path.relative_to(APP_DIR.parent).with_suffix("")
    return _package_of(".".join(relative.parts))


def test_no_package_import_cycles() -> None:
    graph: dict[str, set[str]] = {}
    for path in APP_DIR.rglob("*.py"):
        owner = _source_package(path)
        if owner is None:
            continue
        graph.setdefault(owner, set())
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for module in _imported_modules(tree):
            target = _package_of(module)
            if target and target != owner:
                graph[owner].add(target)
                graph.setdefault(target, set())

    visiting: set[str] = set()
    visited: set[str] = set()
    cycles: list[str] = []

    def visit(node: str, stack: list[str]) -> None:
        if node in visited:
            return
        if node in visiting:
            cycles.append(" -> ".join(stack + [node]))
            return
        visiting.add(node)
        for target in sorted(graph.get(node, ())):
            visit(target, stack + [node])
        visiting.remove(node)
        visited.add(node)

    for node in sorted(graph):
        visit(node, [])

    assert not cycles, "import cycles detected:\n" + "\n".join(cycles)


def test_cross_module_imports_use_public_surface() -> None:
    violations: list[str] = []
    for path in list(MODULES_DIR.rglob("*.py")) + list(MCP_DIR.rglob("*.py")):
        owner = _module_owner(path)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for module in _imported_modules(tree):
            if module.startswith("app.modules."):
                parts = module.split(".")
                other = parts[2] if len(parts) > 2 else ""
                if owner is not None and other == owner:
                    continue
                if not module.endswith(".public"):
                    violations.append(f"{path}: cross-module import {module}")
            if owner is not None and module.startswith("app.mcp"):
                violations.append(f"{path}: business module imports adapter layer")
            if module.startswith("app.api"):
                violations.append(f"{path}: module imports HTTP layer")
    assert not violations, "\n".join(violations)
