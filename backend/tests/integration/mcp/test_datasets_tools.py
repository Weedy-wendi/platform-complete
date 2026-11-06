"""Dataset and project tool integration tests (US2)."""

from __future__ import annotations

import pytest


def rpc(client, headers, method: str, params: dict | None = None, request_id: int = 1):
    payload = {"jsonrpc": "2.0", "id": request_id, "method": method}
    if params is not None:
        payload["params"] = params
    return client.post("/mcp", json=payload, headers=headers)


def call(client, headers, name: str, arguments: dict, request_id: int = 1) -> dict:
    response = rpc(
        client,
        headers,
        "tools/call",
        {"name": name, "arguments": arguments},
        request_id=request_id,
    )
    assert response.status_code == 200
    return response.json()["result"]


def test_list_projects_is_tenant_scoped_and_ordered(seeded_client, auth_headers) -> None:
    result = call(seeded_client, auth_headers, "list_projects", {"limit": 10})
    assert result["isError"] is False
    items = result["structuredContent"]["items"]
    assert [item["id"] for item in items] == ["prj_1", "prj_2", "prj_3"]
    assert all(item["id"] != "prj_other" for item in items)


def test_list_projects_paginates_with_cursor(seeded_client, auth_headers) -> None:
    first = call(seeded_client, auth_headers, "list_projects", {"limit": 1}, request_id=1)
    first_page = first["structuredContent"]
    assert [item["id"] for item in first_page["items"]] == ["prj_1"]
    cursor = first_page["next_cursor"]

    second = call(
        seeded_client,
        auth_headers,
        "list_projects",
        {"limit": 1, "cursor": cursor},
        request_id=2,
    )
    assert [item["id"] for item in second["structuredContent"]["items"]] == ["prj_2"]


def test_tampered_cursor_is_rejected(seeded_client, auth_headers) -> None:
    result = call(seeded_client, auth_headers, "list_projects", {"cursor": "not-a-cursor"})
    assert result["isError"] is True
    assert result["structuredContent"]["code"] == "INVALID_CURSOR"


def test_cursor_cannot_be_reused_for_a_different_query(seeded_client, auth_headers) -> None:
    first = call(seeded_client, auth_headers, "list_projects", {"limit": 1})
    cursor = first["structuredContent"]["next_cursor"]
    result = call(seeded_client, auth_headers, "search_datasets", {"limit": 1, "cursor": cursor})
    assert result["isError"] is True
    assert result["structuredContent"]["code"] == "INVALID_CURSOR"


def test_search_datasets_filters(seeded_client, auth_headers) -> None:
    by_query = call(seeded_client, auth_headers, "search_datasets", {"query": "support"})
    assert [item["id"] for item in by_query["structuredContent"]["items"]] == ["ds_1"]

    by_project = call(seeded_client, auth_headers, "search_datasets", {"project_id": "prj_2"})
    assert [item["id"] for item in by_project["structuredContent"]["items"]] == ["ds_2"]

    by_tags = call(seeded_client, auth_headers, "search_datasets", {"tags": ["support"]})
    assert [item["id"] for item in by_tags["structuredContent"]["items"]] == ["ds_1"]


def test_search_datasets_rejects_invalid_updated_after(seeded_client, auth_headers) -> None:
    result = call(
        seeded_client,
        auth_headers,
        "search_datasets",
        {"updated_after": "not-a-date"},
    )
    assert result["isError"] is True
    assert result["structuredContent"]["code"] == "INVALID_ARGUMENT"


def test_search_datasets_returns_latest_version_and_sample_count(seeded_client, auth_headers) -> None:
    result = call(seeded_client, auth_headers, "search_datasets", {"query": "customer"})
    item = result["structuredContent"]["items"][0]
    assert item["latest_version"] == 2
    assert item["sample_count"] == 3


def test_get_dataset_schema_defaults_to_latest(seeded_client, auth_headers) -> None:
    result = call(seeded_client, auth_headers, "get_dataset_schema", {"dataset_id": "ds_1"})
    payload = result["structuredContent"]
    assert payload["version"] == 2
    assert payload["content_hash"] == "hash-ds1-v2"
    assert payload["row_count"] == 3
    assert {field["name"] for field in payload["fields"]} == {"question", "answer", "metadata"}


def test_get_dataset_schema_explicit_version(seeded_client, auth_headers) -> None:
    result = call(
        seeded_client,
        auth_headers,
        "get_dataset_schema",
        {"dataset_id": "ds_1", "version": 1},
    )
    assert result["structuredContent"]["version"] == 1
    assert result["structuredContent"]["content_hash"] == "hash-ds1-v1"


def test_get_dataset_schema_cross_tenant_is_not_found(seeded_client, auth_headers) -> None:
    result = call(seeded_client, auth_headers, "get_dataset_schema", {"dataset_id": "ds_other"})
    assert result["isError"] is True
    assert result["structuredContent"]["code"] == "NOT_FOUND"


def test_preview_samples_redacts_and_caps_payload(seeded_client, auth_headers) -> None:
    result = call(
        seeded_client,
        auth_headers,
        "preview_samples",
        {"dataset_id": "ds_1", "limit": 50},
    )
    payload = result["structuredContent"]
    assert len(payload["items"]) <= 20
    assert payload["items"]
    assert all(item["redacted"] is True for item in payload["items"])

    by_id = {item["sample_id"]: item for item in payload["items"]}
    assert by_id["samp_1"]["payload"]["email"] == "[EMAIL]"
    assert by_id["samp_2"]["payload"]["phone"] == "[PHONE]"
    assert len(str(by_id["samp_3"]["payload"]).encode("utf-8")) <= 4096
    assert payload["truncated"] is True


def test_preview_samples_cross_tenant_is_not_found(seeded_client, auth_headers) -> None:
    result = call(seeded_client, auth_headers, "preview_samples", {"dataset_id": "ds_other"})
    assert result["isError"] is True
    assert result["structuredContent"]["code"] == "NOT_FOUND"


def test_injection_text_is_returned_as_data(seeded_client, auth_headers) -> None:
    result = call(seeded_client, auth_headers, "preview_samples", {"dataset_id": "ds_1"})
    payload = result["structuredContent"]
    sample = next(item for item in payload["items"] if item["sample_id"] == "samp_2")
    assert "ignore previous instructions" in sample["payload"]["question"]
    assert result["isError"] is False


@pytest.mark.parametrize("tool", ["list_projects", "search_datasets", "get_dataset_schema", "preview_samples"])
def test_dataset_tools_are_read_only(tool, seeded_client, auth_headers) -> None:
    response = rpc(seeded_client, auth_headers, "tools/list", {})
    listed = response.json()["result"]["tools"]
    annotation = next(item["annotations"] for item in listed if item["name"] == tool)
    assert annotation["readOnlyHint"] is True
    assert annotation["destructiveHint"] is False
