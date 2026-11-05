def _rpc(client, headers, method: str, params: dict | None = None, request_id: int = 1):
    payload = {"jsonrpc": "2.0", "id": request_id, "method": method}
    if params is not None:
        payload["params"] = params
    return client.post("/mcp", json=payload, headers=headers)


def test_initialize_and_tools_list(client, auth_headers) -> None:
    initialized = _rpc(
        client,
        auth_headers,
        "initialize",
        {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "pytest", "version": "0"},
        },
    )
    assert initialized.status_code == 200
    result = initialized.json()["result"]
    assert result["protocolVersion"] == "2025-06-18"
    assert "tools" in result["capabilities"]

    listed = _rpc(client, auth_headers, "tools/list", {}, request_id=2)
    assert listed.status_code == 200
    tools = listed.json()["result"]["tools"]
    assert len(tools) == 10
    assert all(tool["annotations"]["readOnlyHint"] is True for tool in tools)


def test_tool_call_success(client, auth_headers) -> None:
    response = _rpc(
        client,
        auth_headers,
        "tools/call",
        {"name": "list_projects", "arguments": {}},
        request_id=3,
    )
    assert response.status_code == 200
    result = response.json()["result"]
    assert result["isError"] is False
    assert result["structuredContent"]["items"] == []


def test_tool_scope_is_reported(client, api_key_service) -> None:
    limited = api_key_service.issue(
        tenant_id="tenant-a",
        name="limited",
        scopes={"mcp:projects:read"},
    )
    headers = {
        "Authorization": f"Bearer {limited.raw_key}",
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
    }
    response = _rpc(client, headers, "tools/call", {"name": "get_run", "arguments": {"run_id": "run_1"}})
    assert response.status_code == 200
    result = response.json()["result"]
    assert result["isError"] is True
    assert result["structuredContent"]["code"] == "FORBIDDEN"


def test_resources_and_health(client, auth_headers) -> None:
    templates = _rpc(client, auth_headers, "resources/templates/list", {})
    assert templates.status_code == 200
    assert len(templates.json()["result"]["resourceTemplates"]) == 3

    assert client.get("/healthz").status_code == 200
    assert client.get("/readyz").status_code == 200
    assert client.get("/metrics").status_code == 200


def test_missing_auth_is_rejected(client) -> None:
    response = _rpc(
        client,
        {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"},
        "tools/list",
        {},
    )
    assert response.status_code == 401
    assert "WWW-Authenticate" in response.headers
