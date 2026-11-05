"""`list_projects` tool handler."""

from __future__ import annotations

import asyncio
from typing import Any

from mcp import types

from app.core.pagination import clamp_limit
from app.mcp.cursor import CursorCodec, query_fingerprint
from app.mcp.format import as_of, drop_none, isoformat_z, success
from app.mcp.pagination import paginate
from app.mcp.registry import ToolCallContext, ToolRegistry
from app.services import ServiceRegistry


def register(registry: ToolRegistry, services: ServiceRegistry, codec: CursorCodec) -> None:
    async def handler(ctx: ToolCallContext, arguments: dict[str, Any]) -> types.CallToolResult:
        limit = clamp_limit(arguments.get("limit"), default=20, maximum=50)
        cursor = arguments.get("cursor")
        query_hash = query_fingerprint({k: v for k, v in arguments.items() if k != "cursor"})
        records = await asyncio.to_thread(services.projects.list_projects, ctx.principal.tenant_id)
        page, next_cursor = paginate(
            records,
            limit=limit,
            cursor=cursor,
            codec=codec,
            tenant_id=ctx.principal.tenant_id,
            tool="list_projects",
            query_hash=query_hash,
            key_fn=lambda project: (
                project.updated_at.isoformat() if project.updated_at else "",
                project.id,
            ),
        )
        payload: dict[str, Any] = {
            "items": [
                drop_none(
                    {
                        "id": project.id,
                        "name": project.name,
                        "description": project.description,
                        "updated_at": isoformat_z(project.updated_at),
                    }
                )
                for project in page
            ],
            "as_of": as_of(),
            "truncated": False,
        }
        if next_cursor:
            payload["next_cursor"] = next_cursor
        return success(payload)

    registry.register_handler("list_projects", handler)
