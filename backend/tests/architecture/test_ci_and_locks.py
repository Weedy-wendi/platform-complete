"""CI and dependency-lock guardrails (T085)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_ci_uses_the_dev_lockfile() -> None:
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "requirements-dev.lock" in workflow
    assert "pip install pytest " not in workflow


def test_dev_lockfile_pins_quality_tools() -> None:
    lock = (ROOT / "backend" / "requirements-dev.lock").read_text(encoding="utf-8")
    for tool in ("pytest==", "pytest-asyncio==", "httpx==", "ruff==", "mypy=="):
        assert tool in lock, tool
