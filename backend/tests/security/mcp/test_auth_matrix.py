from app.modules.identity.public import ALLOWED_SCOPES


def _list(client, headers):
    return client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
        headers=headers,
    )


def _headers(token: str | None) -> dict[str, str]:
    headers = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def test_missing_token(client) -> None:
    response = _list(client, _headers(None))
    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"].startswith("Bearer")


def test_malformed_token(client) -> None:
    response = _list(client, {"Authorization": "Basic abc", "Content-Type": "application/json"})
    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"].startswith("Bearer")


def test_invalid_token_is_rejected(client) -> None:
    response = _list(client, _headers("pk_test_invalid"))
    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"].startswith("Bearer")


def test_revoked_token(client, api_key_service) -> None:
    issued = api_key_service.issue(tenant_id="tenant-a", name="revoked", scopes=ALLOWED_SCOPES)
    assert _list(client, _headers(issued.raw_key)).status_code == 200
    api_key_service.revoke(issued.key_id)
    assert _list(client, _headers(issued.raw_key)).status_code == 401


def test_expired_token(client, api_key_service) -> None:
    from app.core.clock import utcnow_naive

    issued = api_key_service.issue(
        tenant_id="tenant-a",
        name="expired",
        scopes=ALLOWED_SCOPES,
        expires_at=utcnow_naive(),
    )
    assert _list(client, _headers(issued.raw_key)).status_code == 401


def test_valid_token(client, issued_key) -> None:
    response = _list(client, _headers(issued_key.raw_key))
    assert response.status_code == 200
    assert response.json()["result"]["tools"]
