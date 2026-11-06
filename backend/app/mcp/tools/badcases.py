"""Badcase and gate tools (delegate to SRC-05 / GAT-04)."""

from __future__ import annotations

import asyncio
from typing import Any

from mcp import types

from app.core.errors import NotFoundError
from app.core.pagination import clamp_limit
from app.mcp.cursor import CursorCodec, query_fingerprint
from app.mcp.format import as_of, drop_none, isoformat_z, success
from app.mcp.pagination import paginate
from app.mcp.registry import ToolCallContext, ToolRegistry
from app.services import ServiceRegistry


def register(registry: ToolRegistry, services: ServiceRegistry, codec: CursorCodec) -> None:
    async def search_badcases(ctx: ToolCallContext, arguments: dict[str, Any]) -> types.CallToolResult:
        limit = clamp_limit(arguments.get("limit"), default=20, maximum=50)
        cursor = arguments.get("cursor")
        query_hash = query_fingerprint({k: v for k, v in arguments.items() if k != "cursor"})
        result = await asyncio.to_thread(
            services.badcases.search_badcases,
            ctx.principal.tenant_id,
            query=arguments.get("query"),
            dataset_id=arguments.get("dataset_id"),
            tags=tuple(arguments.get("tags") or ()),
            limit=limit,
        )
        page, next_cursor = paginate(
            result.hits,
            limit=limit,
            cursor=cursor,
            codec=codec,
            tenant_id=ctx.principal.tenant_id,
            tool="search_badcases",
            query_hash=query_hash,
            key_fn=lambda hit: (
                hit.similarity if hit.similarity is not None else 0.0,
                hit.badcase.created_at.isoformat() if hit.badcase.created_at else "",
                hit.badcase.id,
            ),
        )
        payload: dict[str, Any] = {
            "items": [
                drop_none(
                    {
                        "badcase_id": hit.badcase.id,
                        "title": hit.badcase.title,
                        "dataset_id": hit.badcase.dataset_id,
                        "sample_id": hit.badcase.sample_id,
                        "tags": list(hit.badcase.tags),
                        "created_at": isoformat_z(hit.badcase.created_at),
                        "similarity": hit.similarity,
                        "evidence_ref": hit.badcase.evidence_ref,
                    }
                )
                for hit in page
            ],
            "degraded": result.degraded,
            "as_of": as_of(),
        }
        if next_cursor:
            payload["next_cursor"] = next_cursor
        return success(payload)

    async def check_gate(ctx: ToolCallContext, arguments: dict[str, Any]) -> types.CallToolResult:
        gate = await asyncio.to_thread(
            services.gate.read_gate,
            tenant_id=ctx.principal.tenant_id,
            suite_id=arguments["suite_id"],
            run_id=arguments["run_id"],
        )
        if gate is None:
            raise NotFoundError("Gate result not found", suite_id=arguments["suite_id"])
        return success(
            {
                "passed": gate.passed,
                "manifest_hash": gate.manifest_hash,
                "evaluated_at": isoformat_z(gate.evaluated_at),
                "rules": [
                    drop_none(
                        {
                            "name": rule.name,
                            "expected": rule.expected,
                            "actual": rule.actual,
                            "passed": rule.passed,
                            "evidence_ref": rule.evidence_ref,
                        }
                    )
                    for rule in gate.rules
                ],
                "as_of": as_of(),
            }
        )

    registry.register_handler("search_badcases", search_badcases)
    registry.register_handler("check_gate", check_gate)
