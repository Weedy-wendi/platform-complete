"""N-1 compatibility guards for schema migrations (QUAL-07 / FR-003).

The checks are static and intentionally strict: a new migration that adds a
destructive upgrade step, forks the revision chain, or is absent from the N-1
runbook fails CI before it can reach a rolling deploy.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]
VERSIONS = BACKEND_ROOT / "migrations" / "versions"
RUNBOOK = BACKEND_ROOT.parent / "docs" / "runbooks" / "n-1-compatibility.md"
EXPECTED_HEAD = "0016_convergence_gaps"

_DESTRUCTIVE_CALLS = frozenset({"drop_table", "drop_column"})
_RAW_DESTRUCTIVE = re.compile(r"\bDROP\s+(?:TABLE|COLUMN)\b", re.IGNORECASE)


@dataclass(frozen=True)
class Revision:
    path: Path
    revision: str
    down_revision: str | None
    source: str
    upgrade_source: str


def _assignment_value(node: ast.Assign | ast.AnnAssign) -> ast.expr | None:
    if isinstance(node, ast.Assign):
        return node.value
    return node.value


def _literal(node: ast.expr | None) -> object:
    if node is None:
        return None
    try:
        return ast.literal_eval(node)
    except (ValueError, SyntaxError):
        return None


def _upgrade_source(source: str, tree: ast.Module) -> str:
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "upgrade":
            return ast.get_source_segment(source, node) or ""
    return ""


def _load_revision(path: Path) -> Revision:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    values: dict[str, object] = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign | ast.AnnAssign):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        for target in targets:
            if isinstance(target, ast.Name) and target.id in {"revision", "down_revision"}:
                values[target.id] = _literal(_assignment_value(node))

    revision = values.get("revision")
    down_revision = values.get("down_revision")
    if not isinstance(revision, str):
        raise AssertionError(f"{path.name}: revision id is missing")
    if down_revision is not None and not isinstance(down_revision, str):
        raise AssertionError(f"{path.name}: down_revision must be a single revision id")
    return Revision(
        path=path,
        revision=revision,
        down_revision=down_revision,
        source=source,
        upgrade_source=_upgrade_source(source, tree),
    )


def _call_name(call: ast.Call) -> str:
    func = call.func
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return ""


def _is_type_narrowing(call: ast.Call) -> bool:
    keywords = {keyword.arg: keyword.value for keyword in call.keywords if keyword.arg}
    type_node = keywords.get("type_")
    if type_node is None:
        return False
    existing_node = keywords.get("existing_type")
    if existing_node is not None and ast.dump(existing_node) == ast.dump(type_node):
        return False
    return True


def destructive_operations(upgrade_source: str) -> list[str]:
    """Return human-readable destructive operations found in an upgrade body."""
    if not upgrade_source.strip():
        return []
    tree = ast.parse(upgrade_source)
    violations: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = _call_name(node)
        if name in _DESTRUCTIVE_CALLS:
            violations.append(name)
        elif name == "alter_column" and _is_type_narrowing(node):
            violations.append("alter_column(type_=...)")
    if _RAW_DESTRUCTIVE.search(upgrade_source):
        violations.append("raw DROP TABLE/COLUMN")
    return violations


def _load_all() -> list[Revision]:
    paths = sorted(VERSIONS.glob("*.py"))
    assert paths, f"no migrations found in {VERSIONS}"
    return [_load_revision(path) for path in paths]


def _doc_names_revision(text: str, revision: Revision) -> bool:
    candidates = {
        revision.revision,
        revision.path.name,
        revision.path.stem,
    }
    if any(candidate in text for candidate in candidates):
        return True
    prefix = revision.revision.split("_", 1)[0]
    return re.search(rf"\b{re.escape(prefix)}\b", text) is not None


def test_upgrades_contain_no_unapproved_destructive_operations() -> None:
    violations: list[str] = []
    for revision in _load_all():
        if "destructive-approved" in revision.source:
            continue
        for operation in destructive_operations(revision.upgrade_source):
            violations.append(f"{revision.path.name}: {operation}")
    assert not violations, "destructive upgrade without '# destructive-approved':\n" + "\n".join(violations)


def test_destructive_detector_catches_future_patterns() -> None:
    snippet = """
def upgrade() -> None:
    op.drop_column("project", "legacy")
    op.alter_column("run", "status", existing_type=sa.String(32), type_=sa.String(8))
    op.execute("DROP TABLE audit_log")
"""
    assert set(destructive_operations(snippet)) == {
        "drop_column",
        "alter_column(type_=...)",
        "raw DROP TABLE/COLUMN",
    }


def test_runbook_documents_every_revision() -> None:
    assert RUNBOOK.is_file(), f"missing N-1 runbook: {RUNBOOK}"
    text = RUNBOOK.read_text(encoding="utf-8")
    missing = [revision.path.name for revision in _load_all() if not _doc_names_revision(text, revision)]
    assert not missing, "N-1 runbook does not name these revisions:\n" + "\n".join(missing)


def test_revision_chain_is_linear_and_head_is_reporting() -> None:
    revisions = _load_all()
    by_revision = {revision.revision: revision for revision in revisions}
    assert len(by_revision) == len(revisions), "duplicate revision ids"

    ordered = sorted(revisions, key=lambda revision: revision.path.name)
    assert ordered[0].down_revision is None, f"{ordered[0].path.name} must be the root migration"

    parents: list[str] = []
    for previous, current in zip(ordered[:-1], ordered[1:], strict=True):
        assert current.down_revision == previous.revision, (
            f"{current.path.name} down_revision={current.down_revision!r} does not continue {previous.revision!r}"
        )
        assert current.down_revision in by_revision
        parents.append(current.down_revision)

    assert len(parents) == len(set(parents)), "migration chain branches or merges"
    heads = [revision.revision for revision in revisions if revision.revision not in set(parents)]
    assert heads == [EXPECTED_HEAD], f"expected single head {EXPECTED_HEAD!r}, found {heads!r}"
