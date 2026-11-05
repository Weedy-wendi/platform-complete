"""Generate public-surface and contract snapshot files for CI (QUAL-01).

Run from the repository root:
    python scripts/generate-public-snapshots.py
"""

from __future__ import annotations

import hashlib
import importlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
SNAPSHOTS = BACKEND / "tests" / "contract" / "snapshots"


def public_surfaces() -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    modules_dir = BACKEND / "app" / "modules"
    for module_dir in sorted(path for path in modules_dir.iterdir() if path.is_dir()):
        if module_dir.name.startswith("_") or not (module_dir / "public.py").exists():
            continue
        module = importlib.import_module(f"app.modules.{module_dir.name}.public")
        exports = getattr(module, "__all__", [])
        result[module_dir.name] = sorted(exports)
    return result


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    SNAPSHOTS.mkdir(parents=True, exist_ok=True)
    (SNAPSHOTS / "public_surfaces.json").write_text(
        json.dumps(public_surfaces(), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    hashes = {
        "openapi": file_hash(ROOT / "specs" / "017-rest-api" / "contracts" / "openapi.yaml"),
        "mcp_tools": file_hash(ROOT / "specs" / "001-mcp-server" / "contracts" / "tools.yaml"),
    }
    (SNAPSHOTS / "contract_hashes.json").write_text(
        json.dumps(hashes, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print("snapshots updated")


if __name__ == "__main__":
    main()
