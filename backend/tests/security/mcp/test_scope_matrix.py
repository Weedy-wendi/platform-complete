"""Scope enforcement matrix (US1, FR-007)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

CONTRACT = Path(__file__).resolve().parents[4] / "specs" / "001-mcp-server" / "contracts" / "tools.yaml"


def _rpc(client, headers, method: str, params: dict | None = None):
    payload = {"jsonrpc": "2.0", "id": 1, "method": method}
    if params is not None:
        payload["params"] = params
    return client.post("/mcp", json=payload, headers=headers)


def _tool_calls() -> list[tuple[str, str, dict]]:
    contract = yaml.safe_load(CONTRACT.read_text(encoding="utf-8"))
    result = []
    for tool in contract["tools"]:
        args: dict = {}
        if "dataset_id" in tool["inputSchema"].get("required", []):
            args["dataset_id"] = "ds_1"
        if "run_id" in tool["inputSchema"].get("required", []):
            args["run_id"] = "run_a"
        if "run_id_a" in tool["inputSchema"].get("required", []):
            args = {"run_id_a": "run_a", "run_id_b": "run_b"}
        if "suite_id" in tool["inputSchema"].get("required", []):
            args["suite_id"] = "suite_1"
        result.append((tool["name"], tool["scope"], args))
    return result


@pytest.mark.parametrize("name,scope,arguments", _tool_calls())
def test_tool_requires_its_scope(name, scope, arguments, seeded_client, api_key_service) -> None:
    # A key with every scope except the one under test.
    other_scopes = {
        "mcp:projects:read",
        "mcp:datasets:read",
        "mcp:eval:read",
        "mcp:eval:read_content",
        "mcp:badcases:read",
        "mcp:gate:read",
    } - {scope}
    issued = api_key_service.issue(tenant_id="tenant-a", name=f"no-{scope}", scopes=other_scopes)
    headers = {
        "Authorization": f"Bearer {issued.raw_key}",
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
    }
    response = _rpc(seeded_client, headers, "tools/call", {"name": name, "arguments": arguments})
    assert response.status_code == 200
    result = response.json()["result"]
    assert result["isError"] is True
    assert result["structuredContent"]["code"] == "FORBIDDEN"
    assert result["structuredContent"]["required_scope"] == scope
