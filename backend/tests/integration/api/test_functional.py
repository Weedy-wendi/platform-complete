"""Functional test run adapter surface."""

from __future__ import annotations


def test_functional_run_create_and_read(client, headers_a, headers_b) -> None:
    created = client.post(
        "/v1/functional/runs",
        headers=headers_a,
        json={"suite_id": "functional-1", "suite_version": "1.0.0"},
    )
    assert created.status_code == 202
    run = created.json()
    assert run["status"] == "queued"

    fetched = client.get(f"/v1/functional/runs/{run['run_id']}", headers=headers_a)
    assert fetched.status_code == 200
    assert fetched.json()["run_id"] == run["run_id"]

    listed = client.get("/v1/functional/runs", headers=headers_a)
    assert [item["run_id"] for item in listed.json()["items"]] == [run["run_id"]]

    assert client.get(f"/v1/functional/runs/{run['run_id']}", headers=headers_b).status_code == 404
