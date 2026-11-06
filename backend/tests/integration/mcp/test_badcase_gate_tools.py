"""Badcase and gate tool integration tests (US4)."""

from __future__ import annotations

from datetime import datetime

from starlette.testclient import TestClient

from app.core.config import Settings
from app.mcp.server import create_app
from app.modules.audit.public import InMemoryAuditWriter
from app.modules.identity.public import ALLOWED_SCOPES, ApiKeyService
from app.services import build_empty_services, build_services
from app.services.badcases import BadcaseService
from app.services.models import Badcase
from app.services.search import UnavailableSemanticSearch
from tests.support.seeds import FakeSemanticSearch


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


def _badcases() -> list[Badcase]:
    return [
        Badcase(
            id="bc_1",
            tenant_id="tenant-a",
            title="Wrong refund policy",
            dataset_id="ds_1",
            sample_id="samp_2",
            tags=("refund",),
            created_at=datetime(2026, 11, 5, 12),
            evidence_ref="evidence://bc_1",
        ),
        Badcase(
            id="bc_other",
            tenant_id="tenant-b",
            title="Other tenant refund",
            dataset_id="ds_other",
            tags=("refund",),
            created_at=datetime(2026, 11, 6, 12),
        ),
    ]


def _client_with_services(settings: Settings, api_key_service: ApiKeyService, services) -> TestClient:
    app = create_app(
        settings,
        api_key_service=api_key_service,
        audit_writer=InMemoryAuditWriter(),
        services=services,
    )
    return TestClient(app)


def test_search_badcases_returns_hits(seeded_client, auth_headers) -> None:
    result = call(seeded_client, auth_headers, "search_badcases", {"query": "refund"})
    payload = result["structuredContent"]
    assert payload["degraded"] is False
    assert [item["badcase_id"] for item in payload["items"]] == ["bc_1"]
    assert payload["items"][0]["dataset_id"] == "ds_1"
    assert payload["items"][0]["sample_id"] == "samp_2"


def test_search_badcases_is_tenant_scoped(seeded_client, auth_headers) -> None:
    result = call(seeded_client, auth_headers, "search_badcases", {})
    payload = result["structuredContent"]
    assert all(item["badcase_id"] != "bc_other" for item in payload["items"])


def test_search_badcases_reports_degraded(settings, api_key_service) -> None:
    services = build_services(
        badcases=BadcaseService(FakeSemanticSearch(_badcases(), degraded=True)),
        gate=build_empty_services().gate,
    )
    client = _client_with_services(settings, api_key_service, services)
    issued = api_key_service.issue(tenant_id="tenant-a", name="degraded", scopes=ALLOWED_SCOPES)
    with client:
        result = call(
            client,
            {
                "Authorization": f"Bearer {issued.raw_key}",
                "Accept": "application/json, text/event-stream",
                "Content-Type": "application/json",
            },
            "search_badcases",
            {"query": "refund"},
        )
    assert result["isError"] is False
    assert result["structuredContent"]["degraded"] is True


def test_search_badcases_upstream_unavailable(settings, api_key_service) -> None:
    services = build_services(
        badcases=BadcaseService(UnavailableSemanticSearch()),
        gate=build_empty_services().gate,
    )
    client = _client_with_services(settings, api_key_service, services)
    issued = api_key_service.issue(tenant_id="tenant-a", name="upstream", scopes=ALLOWED_SCOPES)
    with client:
        result = call(
            client,
            {
                "Authorization": f"Bearer {issued.raw_key}",
                "Accept": "application/json, text/event-stream",
                "Content-Type": "application/json",
            },
            "search_badcases",
            {"query": "refund"},
        )
    assert result["isError"] is True
    assert result["structuredContent"]["code"] == "UPSTREAM_UNAVAILABLE"


def test_check_gate_returns_rules(seeded_client, auth_headers) -> None:
    result = call(
        seeded_client,
        auth_headers,
        "check_gate",
        {"suite_id": "suite_1", "run_id": "run_a"},
    )
    payload = result["structuredContent"]
    assert payload["passed"] is False
    assert [rule["name"] for rule in payload["rules"]] == [
        "accuracy >= 0.9",
        "latency <= 2000ms",
    ]
    failing = payload["rules"][0]
    assert failing["passed"] is False
    assert failing["evidence_ref"] == "evidence://rule/accuracy"


def test_check_gate_not_found(seeded_client, auth_headers) -> None:
    result = call(
        seeded_client,
        auth_headers,
        "check_gate",
        {"suite_id": "suite_1", "run_id": "run_b"},
    )
    assert result["isError"] is True
    assert result["structuredContent"]["code"] == "NOT_FOUND"


def test_check_gate_upstream_unavailable(settings, api_key_service) -> None:
    client = _client_with_services(settings, api_key_service, build_empty_services())
    issued = api_key_service.issue(tenant_id="tenant-a", name="gate", scopes=ALLOWED_SCOPES)
    with client:
        result = call(
            client,
            {
                "Authorization": f"Bearer {issued.raw_key}",
                "Accept": "application/json, text/event-stream",
                "Content-Type": "application/json",
            },
            "check_gate",
            {"suite_id": "suite_1", "run_id": "run_a"},
        )
    assert result["isError"] is True
    assert result["structuredContent"]["code"] == "UPSTREAM_UNAVAILABLE"
