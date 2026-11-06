"""Result-size guarantees (FR-017, T038)."""

from __future__ import annotations

import pytest
from mcp import types

from app.core.context import Principal
from app.core.errors import ResultTooLargeError
from app.mcp.limits import size_bytes
from app.mcp.registry import ToolCallContext, ToolRegistry


def _ctx(registry: ToolRegistry) -> ToolCallContext:
    return ToolCallContext(
        principal=Principal(
            tenant_id="tenant-a",
            subject="user:1",
            scopes=frozenset({"mcp:projects:read"}),
        ),
        tool_name="list_projects",
        tool_version=registry.version,
        trace_id="trace",
    )


@pytest.mark.asyncio
async def test_large_list_is_truncated_under_limit(settings) -> None:
    registry = ToolRegistry.from_contract(settings.mcp_contracts_path, max_result_bytes=settings.mcp_max_result_bytes)

    async def huge(ctx, arguments):
        return types.CallToolResult(
            content=[types.TextContent(text="ok")],
            structured_content={"items": [{"id": str(i), "blob": "x" * 200} for i in range(2000)]},
        )

    registry.register_handler("list_projects", huge)
    result = await registry.call_tool("list_projects", {}, _ctx(registry))
    assert result.is_error is False
    assert result.structured_content["truncated"] is True
    assert size_bytes(result.structured_content) <= settings.mcp_max_result_bytes


@pytest.mark.asyncio
async def test_unshrinkable_object_raises_result_too_large(settings) -> None:
    registry = ToolRegistry.from_contract(settings.mcp_contracts_path, max_result_bytes=settings.mcp_max_result_bytes)

    async def huge(ctx, arguments):
        return types.CallToolResult(
            content=[types.TextContent(text="ok")],
            structured_content={"data": list(range(20000))},
        )

    registry.register_handler("list_projects", huge)
    with pytest.raises(ResultTooLargeError):
        await registry.call_tool("list_projects", {}, _ctx(registry))
