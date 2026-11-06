"""US1 contract tests: initialize, discovery and tool snapshot."""

from __future__ import annotations

from pathlib import Path

import yaml

CONTRACT = Path(__file__).resolve().parents[4] / "specs" / "001-mcp-server" / "contracts" / "tools.yaml"


def rpc(client, headers, method: str, params: dict | None = None, request_id: int = 1):
    payload = {"jsonrpc": "2.0", "id": request_id, "method": method}
    if params is not None:
        payload["params"] = params
    return client.post("/mcp", json=payload, headers=headers)


def test_initialize_returns_protocol_and_capabilities(client, auth_headers) -> None:
    response = rpc(
        client,
        auth_headers,
        "initialize",
        {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "pytest", "version": "0"},
        },
    )
    assert response.status_code == 200
    result = response.json()["result"]
    assert result["protocolVersion"] == "2025-06-18"
    assert result["serverInfo"]["name"] == "pingce-mcp"
    assert "tools" in result["capabilities"]
    assert "resources" in result["capabilities"]


def test_server_is_stateless(client, auth_headers) -> None:
    response = rpc(client, auth_headers, "tools/list", {})
    assert response.status_code == 200
    assert "mcp-session-id" not in {key.lower() for key in response.headers}


def test_tools_list_matches_contract_snapshot(client, auth_headers) -> None:
    contract = yaml.safe_load(CONTRACT.read_text(encoding="utf-8"))
    expected = {tool["name"]: tool for tool in contract["tools"]}

    response = rpc(client, auth_headers, "tools/list", {})
    tools = response.json()["result"]["tools"]
    assert {tool["name"] for tool in tools} == set(expected)
    assert len(tools) == 10

    for tool in tools:
        contract_tool = expected[tool["name"]]
        assert tool["annotations"]["readOnlyHint"] is True
        assert tool["annotations"]["destructiveHint"] is False
        assert tool["annotations"]["idempotentHint"] is True
        assert tool["annotations"]["openWorldHint"] is False
        assert tool["inputSchema"] == contract_tool["inputSchema"]
        assert tool["outputSchema"] == contract_tool["outputSchema"]


def test_tools_list_contains_no_write_verbs(client, auth_headers) -> None:
    tools = rpc(client, auth_headers, "tools/list", {}).json()["result"]["tools"]
    write_prefixes = ("create_", "update_", "delete_", "start_", "cancel_", "write_", "patch_", "remove_", "drop_")
    assert not [tool["name"] for tool in tools if tool["name"].startswith(write_prefixes)]


def test_unsupported_protocol_version_is_rejected(client, auth_headers) -> None:
    headers = dict(auth_headers)
    headers["MCP-Protocol-Version"] = "1999-01-01"
    response = rpc(client, headers, "tools/list", {})
    assert response.status_code == 400
    body = response.json()
    assert "error" in body
    assert body["error"]["code"] != 0
