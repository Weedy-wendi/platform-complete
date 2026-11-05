import asyncio

import pytest
from mcp import types

from app.core.context import Principal
from app.mcp.registry import ToolCallContext, ToolRegistry


def _registry(settings) -> ToolRegistry:
    registry = ToolRegistry.from_contract(settings.mcp_contracts_path, max_result_bytes=settings.mcp_max_result_bytes)
    return registry


def _ctx(registry: ToolRegistry) -> ToolCallContext:
    return ToolCallContext(
        principal=Principal(tenant_id="tenant-a", subject="user:1", scopes=frozenset({"mcp:projects:read"})),
        tool_name="list_projects",
        tool_version=registry.version,
        trace_id="trace",
    )


@pytest.mark.asyncio
async def test_tool_timeout_returns_stable_code(settings) -> None:
    registry = _registry(settings)

    async def slow_handler(ctx, arguments):
        await asyncio.sleep(0.05)
        return types.CallToolResult(content=[types.TextContent(text="late")])

    registry.register_handler("list_projects", slow_handler)
    result = await registry.call_tool_with_timeout("list_projects", {}, _ctx(registry), 0.001)
    assert result.is_error is True
    assert result.structured_content["code"] == "TOOL_TIMEOUT"
    assert result.structured_content["retryable"] is True
