import pytest

from app.core.context import Principal
from app.core.errors import ForbiddenError, InvalidArgumentError
from app.mcp.registry import ToolCallContext, ToolRegistry
from app.mcp.tools import register_default_handlers


def _principal(scopes: set[str]) -> Principal:
    return Principal(tenant_id="tenant-a", subject="user:1", scopes=frozenset(scopes))


def _registry(settings) -> ToolRegistry:
    registry = ToolRegistry.from_contract(settings.mcp_contracts_path, max_result_bytes=settings.mcp_max_result_bytes)
    register_default_handlers(registry)
    return registry


def _ctx(registry: ToolRegistry, principal: Principal, name: str) -> ToolCallContext:
    return ToolCallContext(
        principal=principal,
        tool_name=name,
        tool_version=registry.version,
        trace_id="trace",
    )


def test_registry_contains_ten_read_only_tools(settings) -> None:
    registry = _registry(settings)
    assert len(registry.tool_names) == 10
    for tool in registry.list_tools():
        assert tool.annotations is not None
        assert tool.annotations.read_only_hint is True
        assert tool.annotations.destructive_hint is False
        assert tool.annotations.idempotent_hint is True
        assert tool.annotations.open_world_hint is False


@pytest.mark.asyncio
async def test_list_projects_succeeds_with_empty_page(settings) -> None:
    registry = _registry(settings)
    principal = _principal({"mcp:projects:read"})
    result = await registry.call_tool("list_projects", {}, _ctx(registry, principal, "list_projects"))
    assert result.is_error is False
    assert result.structured_content["items"] == []
    assert "as_of" in result.structured_content


@pytest.mark.asyncio
async def test_scope_is_enforced(settings) -> None:
    registry = _registry(settings)
    principal = _principal({"mcp:projects:read"})
    with pytest.raises(ForbiddenError):
        await registry.call_tool("get_run", {"run_id": "run_1"}, _ctx(registry, principal, "get_run"))


@pytest.mark.asyncio
async def test_invalid_arguments_are_rejected(settings) -> None:
    registry = _registry(settings)
    principal = _principal({"mcp:eval:read"})
    with pytest.raises(InvalidArgumentError):
        await registry.call_tool("get_run", {}, _ctx(registry, principal, "get_run"))


@pytest.mark.asyncio
async def test_registry_without_handlers_returns_stable_code(settings) -> None:
    registry = ToolRegistry.from_contract(settings.mcp_contracts_path, max_result_bytes=settings.mcp_max_result_bytes)
    principal = _principal({"mcp:eval:read"})
    result = await registry.call_tool("get_run", {"run_id": "run_1"}, _ctx(registry, principal, "get_run"))
    assert result.is_error is True
    assert result.structured_content["code"] == "NOT_IMPLEMENTED"
