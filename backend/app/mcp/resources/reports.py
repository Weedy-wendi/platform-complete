"""Run resources: structured summary and Markdown report."""

from __future__ import annotations

import json

from mcp import types

from app.core.context import Principal
from app.core.errors import ForbiddenError
from app.mcp.format import isoformat_z
from app.mcp.tools.evaluation import run_payload
from app.services import ServiceRegistry
from app.services.models import Run

RUN_SCOPE = "mcp:eval:read"
_PREFIX = "pingce://runs/"


def parse_uri(uri: str) -> tuple[str, str] | None:
    if not uri.startswith(_PREFIX):
        return None
    parts = uri[len(_PREFIX) :].split("/")
    if len(parts) != 2 or parts[1] not in {"summary.json", "report.md"}:
        return None
    return parts[0], parts[1]


def render_report(run: Run) -> str:
    lines = [
        f"# Run {run.id}",
        "",
        f"- Status: `{run.status}`",
        f"- Progress: {run.progress:.0%}",
        f"- Manifest hash: `{run.manifest_hash}`",
    ]
    if run.suite_id:
        lines.append(f"- Suite: `{run.suite_id}` v{run.suite_version or '?'}")
    if run.dataset_id:
        lines.append(f"- Dataset: `{run.dataset_id}` v{run.dataset_version or '?'}")
    if run.target:
        lines.append(f"- Target: `{run.target.provider}` / `{run.target.model}`")
    lines.extend(
        [
            f"- Started: {isoformat_z(run.started_at) or '-'}",
            f"- Finished: {isoformat_z(run.finished_at) or '-'}",
            f"- Cost (USD): {run.cost_usd:.4f}",
            "",
            "## Metrics",
            "",
            "| Metric | Value |",
            "|---|---|",
        ]
    )
    if run.metrics:
        lines.extend(f"| {metric.name} | {metric.value} |" for metric in run.metrics)
    else:
        lines.append("| - | - |")
    lines.extend(
        [
            "",
            "## Items",
            "",
            f"- Total: {run.item_total}",
            f"- Succeeded: {run.item_succeeded}",
            f"- Failed: {run.item_failed}",
            f"- Skipped: {run.item_skipped}",
        ]
    )
    if run.error:
        lines.extend(["", "## Error", "", f"`{run.error.code}`: {run.error.message}"])
    return "\n".join(lines) + "\n"


def read_run_resource(
    uri: str,
    *,
    services: ServiceRegistry,
    principal: Principal,
) -> types.ReadResourceResult | None:
    parsed = parse_uri(uri)
    if parsed is None:
        return None
    if not principal.has_scope(RUN_SCOPE):
        raise ForbiddenError("Insufficient scope", required_scope=RUN_SCOPE)
    run_id, kind = parsed
    run = services.evaluation.get_run(principal.tenant_id, run_id)
    if kind == "summary.json":
        mime_type = "application/json"
        text = json.dumps(run_payload(run), ensure_ascii=False, default=str)
    else:
        mime_type = "text/markdown"
        text = render_report(run)
    return types.ReadResourceResult(contents=[types.TextResourceContents(uri=uri, mime_type=mime_type, text=text)])
