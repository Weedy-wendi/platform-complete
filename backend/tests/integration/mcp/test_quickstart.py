"""Quickstart walkthrough (T031, T057).

Mirrors the documented sequence in specs/001-mcp-server/quickstart.md against a
seeded, in-process server.
"""

from __future__ import annotations


def _post(client, headers, payload):
    return client.post("/mcp", json=payload, headers=headers)


def test_quickstart_sequence(seeded_client, auth_headers) -> None:
    headers = dict(auth_headers)
    headers["MCP-Protocol-Version"] = "2025-06-18"

    initialized = _post(
        seeded_client,
        headers,
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "curl", "version": "0.0.1"},
            },
        },
    )
    assert initialized.status_code == 200
    assert initialized.json()["result"]["serverInfo"]["name"] == "pingce-mcp"

    listed = _post(seeded_client, headers, {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
    assert listed.status_code == 200
    tools = listed.json()["result"]["tools"]
    assert len(tools) == 10
    assert all(tool["annotations"]["readOnlyHint"] is True for tool in tools)

    datasets = _post(
        seeded_client,
        headers,
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "search_datasets", "arguments": {"query": "support", "limit": 5}},
        },
    )
    assert datasets.status_code == 200
    dataset_items = datasets.json()["result"]["structuredContent"]["items"]
    assert [item["id"] for item in dataset_items] == ["ds_1"]

    run = _post(
        seeded_client,
        headers,
        {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {"name": "get_run", "arguments": {"run_id": "run_a"}},
        },
    )
    assert run.status_code == 200
    assert run.json()["result"]["structuredContent"]["status"] == "succeeded"


def test_quickstart_read_only_check(seeded_client, auth_headers) -> None:
    headers = dict(auth_headers)
    response = _post(
        seeded_client,
        headers,
        {
            "jsonrpc": "2.0",
            "id": 5,
            "method": "tools/call",
            "params": {"name": "start_eval_run", "arguments": {}},
        },
    )
    assert response.status_code == 200
    assert response.json()["result"]["structuredContent"]["code"] == "NOT_FOUND"
