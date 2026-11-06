"""Read-only promise checks (US1, FR-013/FR-014, T053)."""

from __future__ import annotations

import pytest


def _rpc(client, headers, method: str, params: dict | None = None, request_id: int = 1):
    payload = {"jsonrpc": "2.0", "id": request_id, "method": method}
    if params is not None:
        payload["params"] = params
    return client.post("/mcp", json=payload, headers=headers)


def test_unknown_write_tool_is_not_registered(client, auth_headers) -> None:
    response = _rpc(
        client,
        auth_headers,
        "tools/call",
        {"name": "start_eval_run", "arguments": {"suite_id": "suite_1"}},
    )
    assert response.status_code == 200
    result = response.json()["result"]
    assert result["isError"] is True
    assert result["structuredContent"]["code"] == "NOT_FOUND"


def test_registering_a_write_handler_is_rejected(settings) -> None:
    from app.mcp.registry import ToolRegistry

    registry = ToolRegistry.from_contract(settings.mcp_contracts_path)

    async def handler(ctx, arguments):  # pragma: no cover - never invoked
        raise AssertionError("should not run")

    with pytest.raises(ValueError):
        registry.register_handler("start_eval_run", handler)


def test_tools_list_has_no_write_capability(client, auth_headers) -> None:
    tools = _rpc(client, auth_headers, "tools/list", {}).json()["result"]["tools"]
    assert len(tools) == 10
    assert all(tool["annotations"]["readOnlyHint"] is True for tool in tools)
