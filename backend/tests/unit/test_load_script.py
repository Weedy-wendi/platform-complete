"""Load-test script helpers (T086)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "load-mcp.py"

_spec = importlib.util.spec_from_file_location("load_mcp", SCRIPT)
assert _spec is not None and _spec.loader is not None
load_mcp = importlib.util.module_from_spec(_spec)
sys.modules["load_mcp"] = load_mcp
_spec.loader.exec_module(load_mcp)


def test_default_metrics_url_uses_sibling_endpoint() -> None:
    assert load_mcp._default_metrics_url("http://127.0.0.1:8765/mcp") == "http://127.0.0.1:8765/metrics"
    assert load_mcp._default_metrics_url("https://host/base/mcp") == "https://host/base/metrics"


def test_parse_process_memory() -> None:
    text = "# HELP process_resident_memory_bytes ...\nprocess_resident_memory_bytes 1.5e+08\n"
    assert load_mcp._parse_memory(text) == 1.5e8
    assert load_mcp._parse_memory("no process metrics") is None


def test_percentile() -> None:
    assert load_mcp._percentile([10.0, 20.0, 30.0], 0.50) == 20.0
    assert load_mcp._percentile([1.0, 2.0, 3.0, 4.0], 0.95) == 4.0
    assert load_mcp._percentile([], 0.95) == 0.0
