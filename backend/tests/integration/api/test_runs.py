"""Run lifecycle, items, comparison, cancellation and evaluators."""

from __future__ import annotations

RUN_BODY = {
    "suite_id": "suite-1",
    "suite_version": "1.0.0",
    "dataset_id": "dataset-1",
    "dataset_version": 1,
    "target_config": {"provider": "openai", "model": "gpt-4.1"},
}


def _create_run(client, headers) -> str:
    response = client.post("/v1/runs", headers=headers, json=RUN_BODY)
    assert response.status_code == 202
    return response.json()["run_id"]


def test_run_lifecycle(client, headers_a, headers_b) -> None:
    created = client.post("/v1/runs", headers=headers_a, json=RUN_BODY)
    assert created.status_code == 202
    body = created.json()
    assert body["status"] == "queued"
    assert body["manifest_hash"]
    run_id = body["run_id"]

    listed = client.get("/v1/runs", headers=headers_a, params={"suite_id": "suite-1"})
    assert listed.status_code == 200
    assert [item["run_id"] for item in listed.json()["items"]] == [run_id]

    fetched = client.get(f"/v1/runs/{run_id}", headers=headers_a)
    assert fetched.status_code == 200
    assert fetched.json()["status"] == "queued"

    items = client.get(f"/v1/runs/{run_id}/items", headers=headers_a)
    assert items.status_code == 200
    assert items.json()["items"] == []

    cancelled = client.post(f"/v1/runs/{run_id}/cancel", headers=headers_a)
    assert cancelled.status_code == 202
    assert cancelled.json()["status"] == "cancelled"

    again = client.post(f"/v1/runs/{run_id}/cancel", headers=headers_a)
    assert again.status_code == 409
    assert again.json()["code"] == "CONFLICT"

    assert client.get(f"/v1/runs/{run_id}", headers=headers_b).status_code == 404
    assert client.get("/v1/runs", headers=headers_b).json()["items"] == []


def test_run_comparison(client, headers_a) -> None:
    candidate = _create_run(client, headers_a)
    baseline = _create_run(client, headers_a)

    response = client.get(
        f"/v1/runs/{candidate}/compare",
        headers=headers_a,
        params={"baseline_run_id": baseline},
    )
    assert response.status_code == 200
    assert response.json()["metrics"] == []
    assert response.json()["warnings"] == []


def test_run_create_is_idempotent(client, headers_a) -> None:
    headers = {**headers_a, "Idempotency-Key": "run-once"}
    first = client.post("/v1/runs", headers=headers, json=RUN_BODY)
    second = client.post("/v1/runs", headers=headers, json=RUN_BODY)
    assert first.status_code == 202
    assert second.status_code == 202
    assert first.json()["run_id"] == second.json()["run_id"]


def test_evaluator_crud(client, headers_a, headers_b) -> None:
    created = client.post(
        "/v1/evaluators",
        headers=headers_a,
        json={
            "name": "Correctness",
            "version": "1.0.0",
            "kind": "judge",
            "metrics": [{"name": "accuracy", "direction": "higher_is_better"}],
        },
    )
    assert created.status_code == 201
    evaluator = created.json()
    assert evaluator["kind"] == "judge"

    listed = client.get("/v1/evaluators", headers=headers_a)
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()["items"]] == [evaluator["id"]]

    assert client.get("/v1/evaluators", headers=headers_b).json()["items"] == []


def test_run_requires_write_scope(client, headers_a) -> None:
    read_only = {**headers_a, "Authorization": "Bearer pk_test_no_scope_secret"}
    response = client.post("/v1/runs", headers=read_only, json=RUN_BODY)
    assert response.status_code == 403
