"""Evaluation tools: evaluators, runs, run items and comparison."""

from __future__ import annotations

import asyncio
from typing import Any

from mcp import types

from app.core.errors import ForbiddenError
from app.core.pagination import clamp_limit
from app.mcp.cursor import CursorCodec, query_fingerprint
from app.mcp.format import as_of, drop_none, isoformat_z, success
from app.mcp.limits import MAX_STRING_BYTES, redact_text, truncate_utf8
from app.mcp.pagination import paginate
from app.mcp.registry import ToolCallContext, ToolRegistry
from app.services import ServiceRegistry
from app.services.models import Run, RunItem

CONTENT_SCOPE = "mcp:eval:read_content"


def run_payload(run: Run) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "run_id": run.id,
        "status": run.status,
        "progress": run.progress,
        "manifest_hash": run.manifest_hash,
        "summary": {
            "metrics": [{"name": metric.name, "value": metric.value} for metric in run.metrics],
            "cost_usd": run.cost_usd,
            "item_counts": {
                "total": run.item_total,
                "succeeded": run.item_succeeded,
                "failed": run.item_failed,
                "skipped": run.item_skipped,
            },
        },
        "as_of": as_of(),
    }
    optional = {
        "suite_id": run.suite_id,
        "suite_version": run.suite_version,
        "dataset_id": run.dataset_id,
        "dataset_version": run.dataset_version,
        "started_at": isoformat_z(run.started_at),
        "finished_at": isoformat_z(run.finished_at),
    }
    payload.update(drop_none(optional))
    if run.target is not None:
        payload["target"] = {"provider": run.target.provider, "model": run.target.model}
    if run.error is not None:
        payload["error"] = {"code": run.error.code, "message": run.error.message}
    return payload


def _metric_score(item: RunItem, metric: str | None) -> float | None:
    if metric:
        for value in item.metrics:
            if value.name == metric:
                return value.value
        return None
    return item.score


def _item_payload(item: RunItem, *, include_io: bool, metric: str | None) -> dict[str, Any]:
    payload = drop_none(
        {
            "item_id": item.id,
            "sample_id": item.sample_id,
            "status": item.status,
            "score": _metric_score(item, metric),
            "latency_ms": item.latency_ms,
            "tokens": item.tokens,
            "evidence_ref": item.evidence_ref,
        }
    )
    if item.error is not None:
        payload["error"] = {"code": item.error.code, "message": item.error.message}
    if include_io:
        if item.input is not None:
            payload["input"] = truncate_utf8(redact_text(item.input), MAX_STRING_BYTES)
        if item.output is not None:
            payload["output"] = truncate_utf8(redact_text(item.output), MAX_STRING_BYTES)
    return payload


def register(registry: ToolRegistry, services: ServiceRegistry, codec: CursorCodec) -> None:
    async def list_evaluators(ctx: ToolCallContext, arguments: dict[str, Any]) -> types.CallToolResult:
        evaluators = await asyncio.to_thread(
            services.evaluation.list_evaluators,
            ctx.principal.tenant_id,
            arguments.get("project_id"),
        )
        return success(
            {
                "items": [
                    drop_none(
                        {
                            "id": evaluator.id,
                            "name": evaluator.name,
                            "version": evaluator.version,
                            "kind": evaluator.kind,
                            "description": evaluator.description,
                            "metrics": [
                                {"name": metric.name, "direction": metric.direction} for metric in evaluator.metrics
                            ],
                        }
                    )
                    for evaluator in evaluators
                ],
                "as_of": as_of(),
            }
        )

    async def get_run(ctx: ToolCallContext, arguments: dict[str, Any]) -> types.CallToolResult:
        run = await asyncio.to_thread(services.evaluation.get_run, ctx.principal.tenant_id, arguments["run_id"])
        return success(run_payload(run))

    async def get_run_items(ctx: ToolCallContext, arguments: dict[str, Any]) -> types.CallToolResult:
        include_io = bool(arguments.get("include_io", False))
        if include_io and not ctx.principal.has_scope(CONTENT_SCOPE):
            raise ForbiddenError("include_io requires scope mcp:eval:read_content", required_scope=CONTENT_SCOPE)
        status = arguments.get("status")
        metric = arguments.get("metric")
        min_score = arguments.get("min_score")
        limit = clamp_limit(arguments.get("limit"), default=20, maximum=100)
        cursor = arguments.get("cursor")
        query_hash = query_fingerprint({k: v for k, v in arguments.items() if k != "cursor"})

        items = await asyncio.to_thread(
            services.evaluation.list_items,
            ctx.principal.tenant_id,
            arguments["run_id"],
        )
        if status:
            items = [item for item in items if item.status == status]
        if metric:
            items = [item for item in items if any(value.name == metric for value in item.metrics)]
        if min_score is not None:
            items = [
                item
                for item in items
                if (score := _metric_score(item, metric)) is not None and score >= float(min_score)
            ]

        page, next_cursor = paginate(
            items,
            limit=limit,
            cursor=cursor,
            codec=codec,
            tenant_id=ctx.principal.tenant_id,
            tool="get_run_items",
            query_hash=query_hash,
            key_fn=lambda item: (item.id,),
        )
        result: dict[str, Any] = {
            "items": [_item_payload(item, include_io=include_io, metric=metric) for item in page],
            "as_of": as_of(),
            "truncated": False,
        }
        if next_cursor:
            result["next_cursor"] = next_cursor
        return success(result)

    async def compare_runs(ctx: ToolCallContext, arguments: dict[str, Any]) -> types.CallToolResult:
        comparison = await asyncio.to_thread(
            services.evaluation.compare_runs,
            ctx.principal.tenant_id,
            arguments["run_id_a"],
            arguments["run_id_b"],
            arguments.get("metrics"),
        )
        return success(
            {
                "metrics": [
                    {
                        "name": item.name,
                        "baseline": item.baseline,
                        "candidate": item.candidate,
                        "delta": item.delta,
                        "delta_pct": item.delta_pct,
                        "significant": item.significant,
                    }
                    for item in comparison.metrics
                ],
                "regressions": [{"metric": item.name, "delta": item.delta} for item in comparison.regressions],
                "improvements": [{"metric": item.name, "delta": item.delta} for item in comparison.improvements],
                "warnings": comparison.warnings,
                "as_of": as_of(),
            }
        )

    registry.register_handler("list_evaluators", list_evaluators)
    registry.register_handler("get_run", get_run)
    registry.register_handler("get_run_items", get_run_items)
    registry.register_handler("compare_runs", compare_runs)
