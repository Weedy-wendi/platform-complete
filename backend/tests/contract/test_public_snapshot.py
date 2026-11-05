"""Public-surface and contract snapshot checks (QUAL-01)."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SNAPSHOTS = Path(__file__).resolve().parent / "snapshots"


def _generator():
    path = ROOT / "scripts" / "generate_public_snapshots.py"
    spec = importlib.util.spec_from_file_location("generate_public_snapshots", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_public_surfaces_match_snapshot() -> None:
    expected = json.loads((SNAPSHOTS / "public_surfaces.json").read_text(encoding="utf-8"))
    assert _generator().public_surfaces() == expected


def test_contract_hashes_match_snapshot() -> None:
    expected = json.loads((SNAPSHOTS / "contract_hashes.json").read_text(encoding="utf-8"))
    generator = _generator()
    actual = {
        "openapi": generator.file_hash(ROOT / "specs" / "017-rest-api" / "contracts" / "openapi.yaml"),
        "mcp_tools": generator.file_hash(ROOT / "specs" / "001-mcp-server" / "contracts" / "tools.yaml"),
    }
    assert actual == expected
