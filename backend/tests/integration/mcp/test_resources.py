"""Resource integration tests (T060-T062, T083)."""

from __future__ import annotations

import json

from starlette.testclient import TestClient

from app.mcp.server import create_app
from app.modules.audit.public import InMemoryAuditWriter
from app.modules.identity.public import ALLOWED_SCOPES
from app.services import build_services


def rpc(client, headers, method: str, params: dict | None = None, request_id: int = 1):
    payload = {"jsonrpc": "2.0", "id": request_id, "method": method}
    if params is not None:
        payload["params"] = params
    return client.post("/mcp", json=payload, headers=headers)


def _read(client, headers, uri: str, request_id: int = 1) -> dict:
    response = rpc(client, headers, "resources/read", {"uri": uri}, request_id=request_id)
    assert response.status_code == 200
    return response.json()


def test_three_resource_templates_are_registered(seeded_client, auth_headers) -> None:
    response = rpc(seeded_client, auth_headers, "resources/templates/list", {})
    templates = response.json()["result"]["resourceTemplates"]
    assert len(templates) == 3
    assert {template["name"] for template in templates} == {"dataset-schema", "run-summary", "run-report"}


def test_list_resources_is_readable(seeded_client, auth_headers) -> None:
    response = rpc(seeded_client, auth_headers, "resources/list", {})
    assert response.status_code == 200
    assert "resources" in response.json()["result"]


def test_read_dataset_schema_resource(seeded_client, auth_headers) -> None:
    body = _read(seeded_client, auth_headers, "pingce://datasets/ds_1/versions/2/schema")
    content = body["result"]["contents"][0]
    assert content["mimeType"] == "application/json"
    payload = json.loads(content["text"])
    assert payload["dataset_id"] == "ds_1"
    assert payload["version"] == 2
    assert payload["content_hash"] == "hash-ds1-v2"


def test_read_run_summary_resource(seeded_client, auth_headers) -> None:
    body = _read(seeded_client, auth_headers, "pingce://runs/run_a/summary.json")
    content = body["result"]["contents"][0]
    payload = json.loads(content["text"])
    assert payload["run_id"] == "run_a"
    assert payload["manifest_hash"] == "manifest-a"


def test_read_run_report_resource(seeded_client, auth_headers) -> None:
    body = _read(seeded_client, auth_headers, "pingce://runs/run_a/report.md")
    content = body["result"]["contents"][0]
    assert content["mimeType"] == "text/markdown"
    assert "# Run run_a" in content["text"]
    assert "accuracy" in content["text"]


def _assert_error(body: dict, code: str) -> None:
    assert body["error"]["code"] == -32000
    assert body["error"]["data"]["code"] == code
    assert body["error"]["data"]["trace_id"]


def test_dataset_resource_is_tenant_isolated(seeded_client, auth_headers) -> None:
    body = _read(seeded_client, auth_headers, "pingce://datasets/ds_other/versions/1/schema")
    _assert_error(body, "NOT_FOUND")


def test_run_resource_is_tenant_isolated(seeded_client, auth_headers) -> None:
    body = _read(seeded_client, auth_headers, "pingce://runs/run_other/summary.json")
    _assert_error(body, "NOT_FOUND")


def test_unknown_resource_is_not_found(seeded_client, auth_headers) -> None:
    body = _read(seeded_client, auth_headers, "pingce://unknown/thing")
    _assert_error(body, "NOT_FOUND")


def test_resource_requires_matching_scope(seeded_client, api_key_service) -> None:
    issued = api_key_service.issue(tenant_id="tenant-a", name="eval-only", scopes={"mcp:eval:read"})
    headers = {
        "Authorization": f"Bearer {issued.raw_key}",
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
    }
    body = _read(seeded_client, headers, "pingce://datasets/ds_1/versions/2/schema")
    _assert_error(body, "FORBIDDEN")
    assert body["error"]["data"]["required_scope"] == "mcp:datasets:read"


class BrokenDatasets:
    def get_schema(self, *args, **kwargs):
        raise RuntimeError("internal path C:\\secret\\db.py")

    def search_datasets(self, *args, **kwargs):
        raise RuntimeError("internal")

    def list_samples(self, *args, **kwargs):
        raise RuntimeError("internal")


def test_unexpected_resource_error_is_masked(settings, api_key_service) -> None:
    services = build_services(datasets=BrokenDatasets())
    app = create_app(
        settings,
        api_key_service=api_key_service,
        audit_writer=InMemoryAuditWriter(),
        services=services,
    )
    issued = api_key_service.issue(tenant_id="tenant-a", name="broken", scopes=ALLOWED_SCOPES)
    headers = {
        "Authorization": f"Bearer {issued.raw_key}",
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
    }
    with TestClient(app) as client:
        body = _read(client, headers, "pingce://datasets/ds_1/versions/1/schema")
    assert body["error"]["code"] == -32603
    assert body["error"]["data"]["code"] == "INTERNAL"
    assert body["error"]["data"]["trace_id"]
    assert "internal path" not in json.dumps(body)
