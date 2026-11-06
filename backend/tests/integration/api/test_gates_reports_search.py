"""Gate results, report exports and badcase search."""

from __future__ import annotations

from app.api.memory import InMemoryGates, InMemorySearch
from app.api.ports import BadcaseHitRecord, GateRecord, GateRuleRecord
from app.core.clock import utcnow

RUN_BODY = {
    "suite_id": "suite-1",
    "dataset_id": "dataset-1",
    "dataset_version": 1,
}


def test_gate_result_is_tenant_scoped(client, headers_a, headers_b, api_services) -> None:
    gates = api_services.gates
    assert isinstance(gates, InMemoryGates)
    gates.put(
        tenant_id="tenant-a",
        suite_id="suite-1",
        run_id="run-1",
        gate=GateRecord(
            passed=False,
            manifest_hash="manifest-1",
            evaluated_at=utcnow(),
            rules=(
                GateRuleRecord(
                    name="accuracy >= 0.9",
                    expected="0.9",
                    actual="0.8",
                    passed=False,
                    evidence_ref="evidence://gate/rule-1",
                ),
            ),
        ),
    )

    response = client.get("/v1/gates/suite-1/run-1", headers=headers_a)
    assert response.status_code == 200
    body = response.json()
    assert body["passed"] is False
    assert body["rules"][0]["evidence_ref"] == "evidence://gate/rule-1"

    assert client.get("/v1/gates/suite-1/run-1", headers=headers_b).status_code == 404


def test_report_json_and_markdown(client, headers_a, headers_b) -> None:
    created = client.post("/v1/runs", headers=headers_a, json=RUN_BODY)
    run_id = created.json()["run_id"]

    json_report = client.get(f"/v1/reports/{run_id}", headers=headers_a)
    assert json_report.status_code == 200
    assert json_report.headers["content-type"].startswith("application/json")
    assert json_report.json()["run_id"] == run_id

    markdown = client.get(f"/v1/reports/{run_id}", headers=headers_a, params={"format": "markdown"})
    assert markdown.status_code == 200
    assert markdown.headers["content-type"].startswith("text/markdown")
    assert run_id in markdown.text

    assert client.get(f"/v1/reports/{run_id}", headers=headers_b).status_code == 404


def test_badcase_search_filters_by_tenant_and_tags(client, headers_a, headers_b, api_services) -> None:
    search = api_services.search
    assert isinstance(search, InMemorySearch)
    search.add(
        BadcaseHitRecord(
            badcase_id="bc-a",
            title="Wrong refund policy",
            tenant_id="tenant-a",
            dataset_id="dataset-1",
            tags=("refund", "policy"),
            similarity=0.9,
            evidence_ref="evidence://bc-a",
        )
    )
    search.add(
        BadcaseHitRecord(
            badcase_id="bc-b",
            title="Other tenant refund",
            tenant_id="tenant-b",
            dataset_id="dataset-1",
            tags=("refund",),
            similarity=0.95,
        )
    )

    response = client.post(
        "/v1/badcases/search",
        headers=headers_a,
        json={"query": "refund", "tags": ["policy"], "limit": 10},
    )
    assert response.status_code == 200
    body = response.json()
    assert [item["badcase_id"] for item in body["items"]] == ["bc-a"]
    assert body["degraded"] is True

    other = client.post("/v1/badcases/search", headers=headers_b, json={"query": "refund"})
    assert [item["badcase_id"] for item in other.json()["items"]] == ["bc-b"]
