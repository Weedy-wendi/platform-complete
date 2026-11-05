"""Runtime and iteration assets required by QUAL-04/QUAL-10."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
DASHBOARDS = ROOT / "deploy" / "grafana" / "dashboards"


def test_four_operational_dashboards_exist() -> None:
    titles = {path: json.loads(path.read_text(encoding="utf-8"))["title"] for path in sorted(DASHBOARDS.glob("*.json"))}
    assert titles, "no Grafana dashboards found"
    joined = " ".join(titles.values()).lower()
    for required in ("queue", "error", "latency", "cost"):
        assert required in joined, f"missing {required} dashboard"


def test_dashboards_have_panels() -> None:
    for path in sorted(DASHBOARDS.glob("*.json")):
        document = json.loads(path.read_text(encoding="utf-8"))
        assert document["panels"], f"{path.name} has no panels"


def test_alerts_parse() -> None:
    document = yaml.safe_load((ROOT / "deploy" / "prometheus" / "alerts.yaml").read_text(encoding="utf-8"))
    assert document["groups"]


def test_dependency_security_updates_configured() -> None:
    document = yaml.safe_load((ROOT / ".github" / "dependabot.yml").read_text(encoding="utf-8"))
    ecosystems = {entry["package-ecosystem"] for entry in document["updates"]}
    assert {"pip", "npm", "github-actions"} <= ecosystems


def test_canary_and_rollback_runbooks_exist() -> None:
    assert (ROOT / "docs" / "runbooks" / "canary.md").is_file()
    assert (ROOT / "docs" / "runbooks" / "rollback.md").is_file()
    assert (ROOT / "docs" / "runbooks" / "kill-switch.md").is_file()
