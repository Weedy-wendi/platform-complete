"""Snapshot rendering: JSON and Markdown, plus comparison summaries."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from typing import Any

from app.modules.evaluation.public import ComparisonView, RunItemView, RunView


def content_hash(content: str | bytes) -> str:
    data = content.encode("utf-8") if isinstance(content, str) else content
    return hashlib.sha256(data).hexdigest()


def _json(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=False, default=str)


def run_payload(run: RunView, items: list[RunItemView]) -> dict[str, Any]:
    return {
        "run": asdict(run),
        "metrics": [asdict(summary) for summary in run.metrics],
        "items": [asdict(item) for item in items],
    }


def render_run_json(run: RunView, items: list[RunItemView]) -> str:
    return _json(run_payload(run, items))


def _cell(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def _number(value: float) -> str:
    return f"{value:.6f}"


def render_run_markdown(run: RunView, items: list[RunItemView]) -> str:
    lines = [
        f"# Run {run.run_id}",
        "",
        f"- Status: `{run.status}`",
        f"- Mode: `{run.mode}`",
        f"- Progress: {run.progress}%",
        f"- Manifest hash: `{run.manifest_hash}`",
        f"- Dataset: `{run.dataset_id}` v{run.dataset_version}",
    ]
    if run.suite_id:
        lines.append(f"- Suite: `{run.suite_id}` v{run.suite_version or '?'}")
    lines.extend(
        [
            f"- Cost (USD): {run.cost_usd:.6f}",
            f"- Budget (USD): {run.budget_usd if run.budget_usd is not None else '-'}",
            "",
            "## Metrics",
            "",
            "| Metric | Value | Count | Stddev | Direction |",
            "|---|---|---|---|---|",
        ]
    )
    if run.metrics:
        lines.extend(
            f"| {_cell(metric.name)} | {_number(metric.value)} | {metric.count} | "
            f"{_number(metric.stdev)} | {_cell(metric.direction)} |"
            for metric in run.metrics
        )
    else:
        lines.append("| - | - | - | - | - |")
    lines.extend(
        [
            "",
            "## Items",
            "",
            f"- Total: {run.total_items}",
            f"- Succeeded: {run.succeeded_items}",
            f"- Failed: {run.failed_items}",
            f"- Skipped: {run.skipped_items}",
        ]
    )
    failed = [item for item in items if item.status == "failed"]
    if failed:
        lines.extend(["", "## Failed items", "", "| Sample | Error |", "|---|---|"])
        lines.extend(f"| {_cell(item.sample_key)} | {_cell(item.error or '')} |" for item in failed[:50])
    if run.error:
        lines.extend(["", "## Error", "", f"`{run.error}`"])
    return "\n".join(lines).rstrip() + "\n"


def comparison_payload(comparison: ComparisonView) -> dict[str, Any]:
    return {
        "run_a": comparison.run_a,
        "run_b": comparison.run_b,
        "comparable": comparison.comparable,
        "metrics": [asdict(metric) for metric in comparison.metrics],
        "regressions": [asdict(metric) for metric in comparison.regressions],
        "improvements": [asdict(metric) for metric in comparison.improvements],
        "warnings": comparison.warnings,
    }


def render_comparison_json(comparison: ComparisonView) -> str:
    return _json(comparison_payload(comparison))


def render_comparison_markdown(comparison: ComparisonView) -> str:
    lines = [
        f"# Comparison: {comparison.run_a} -> {comparison.run_b}",
        "",
        f"- Comparable: `{comparison.comparable}`",
        "",
        "## Metrics",
        "",
        "| Metric | Baseline | Candidate | Delta | Delta % | Significant | CI |",
        "|---|---|---|---|---|---|---|",
    ]
    for metric in comparison.metrics:
        interval = (
            f"[{metric.ci_low:.6f}, {metric.ci_high:.6f}]"
            if metric.ci_low is not None and metric.ci_high is not None
            else "-"
        )
        lines.append(
            f"| {_cell(metric.name)} | {_number(metric.baseline)} | {_number(metric.candidate)} | "
            f"{_number(metric.delta)} | {metric.delta_pct:.4f}% | {metric.significant} | {interval} |"
        )
    if not comparison.metrics:
        lines.append("| - | - | - | - | - | - | - |")
    if comparison.regressions:
        lines.extend(["", "## Regressions", ""])
        lines.extend(
            f"- {_cell(metric.name)}: {metric.delta_pct:.4f}% (significant={metric.significant})"
            for metric in comparison.regressions
        )
    if comparison.improvements:
        lines.extend(["", "## Improvements", ""])
        lines.extend(f"- {_cell(metric.name)}: +{metric.delta_pct:.4f}%" for metric in comparison.improvements)
    if comparison.warnings:
        lines.extend(["", "## Warnings", ""])
        lines.extend(f"- {warning}" for warning in comparison.warnings)
    return "\n".join(lines).rstrip() + "\n"
