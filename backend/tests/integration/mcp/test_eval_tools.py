"""Evaluation tool integration tests (US3)."""

from __future__ import annotations

import pytest

from app.services.models import Run
from tests.conftest import make_headers


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


def test_list_evaluators_returns_published_only(seeded_client, auth_headers) -> None:
    result = call(seeded_client, auth_headers, "list_evaluators", {})
    ids = [item["id"] for item in result["structuredContent"]["items"]]
    assert "evaluator_draft" not in ids
    assert set(ids) == {"evaluator_1", "evaluator_2"}


def test_list_evaluators_filters_by_project(seeded_client, auth_headers) -> None:
    result = call(seeded_client, auth_headers, "list_evaluators", {"project_id": "prj_1"})
    ids = {item["id"] for item in result["structuredContent"]["items"]}
    assert ids == {"evaluator_1", "evaluator_2"}


def test_get_run_returns_status_and_summary(seeded_client, auth_headers) -> None:
    result = call(seeded_client, auth_headers, "get_run", {"run_id": "run_a"})
    payload = result["structuredContent"]
    assert payload["run_id"] == "run_a"
    assert payload["status"] == "succeeded"
    assert payload["progress"] == 1.0
    assert payload["manifest_hash"] == "manifest-a"
    assert payload["summary"]["item_counts"] == {"total": 3, "succeeded": 2, "failed": 1, "skipped": 0}
    assert payload["summary"]["cost_usd"] == 1.25
    assert {metric["name"] for metric in payload["summary"]["metrics"]} == {"accuracy", "latency_ms"}


def test_get_run_cross_tenant_is_not_found(seeded_client, auth_headers) -> None:
    result = call(seeded_client, auth_headers, "get_run", {"run_id": "run_other"})
    assert result["isError"] is True
    assert result["structuredContent"]["code"] == "NOT_FOUND"


def test_get_run_items_defaults_to_no_io(seeded_client, auth_headers) -> None:
    result = call(seeded_client, auth_headers, "get_run_items", {"run_id": "run_a", "status": "failed"})
    items = result["structuredContent"]["items"]
    assert [item["item_id"] for item in items] == ["item_2"]
    assert "input" not in items[0]
    assert "output" not in items[0]
    assert items[0]["error"]["code"] == "JUDGE_FAILED"


def test_get_run_items_include_io_requires_content_scope(seeded_client, api_key_service) -> None:
    limited = api_key_service.issue(
        tenant_id="tenant-a",
        name="eval-read-only",
        scopes={"mcp:eval:read"},
    )
    result = call(
        seeded_client,
        make_headers(limited.raw_key),
        "get_run_items",
        {"run_id": "run_a", "include_io": True},
    )
    assert result["isError"] is True
    assert result["structuredContent"]["code"] == "FORBIDDEN"
    assert result["structuredContent"]["required_scope"] == "mcp:eval:read_content"


def test_get_run_items_include_io_redacts(seeded_client, auth_headers) -> None:
    result = call(
        seeded_client,
        auth_headers,
        "get_run_items",
        {"run_id": "run_a", "status": "succeeded", "limit": 10, "include_io": True},
    )
    item = next(item for item in result["structuredContent"]["items"] if item["item_id"] == "item_1")
    assert "input" in item
    assert "alice@example.com" not in item["input"]
    assert "[EMAIL]" in item["input"]


def test_get_run_items_paginates(seeded_client, auth_headers) -> None:
    first = call(seeded_client, auth_headers, "get_run_items", {"run_id": "run_a", "limit": 1})
    cursor = first["structuredContent"]["next_cursor"]
    assert cursor
    second = call(
        seeded_client,
        auth_headers,
        "get_run_items",
        {"run_id": "run_a", "limit": 1, "cursor": cursor},
    )
    assert second["structuredContent"]["items"]
    assert second["structuredContent"]["items"][0]["item_id"] != first["structuredContent"]["items"][0]["item_id"]


def test_compare_runs_marks_regressions_and_improvements(seeded_client, auth_headers) -> None:
    result = call(
        seeded_client,
        auth_headers,
        "compare_runs",
        {"run_id_a": "run_a", "run_id_b": "run_b"},
    )
    payload = result["structuredContent"]
    metrics = {metric["name"]: metric for metric in payload["metrics"]}
    assert metrics["accuracy"]["delta"] == pytest.approx(-0.05)
    assert metrics["latency_ms"]["delta"] == pytest.approx(-100)
    assert "accuracy" in {item["metric"] for item in payload["regressions"]}
    assert "latency_ms" in {item["metric"] for item in payload["improvements"]}
    assert any("different dataset versions" in warning for warning in payload["warnings"])


def test_mcp_get_run_matches_service(seeded_client, auth_headers, seeded_services) -> None:
    result = call(seeded_client, auth_headers, "get_run", {"run_id": "run_a"})
    service_run: Run = seeded_services.evaluation.get_run("tenant-a", "run_a")
    assert result["structuredContent"]["manifest_hash"] == service_run.manifest_hash
    assert result["structuredContent"]["status"] == service_run.status
