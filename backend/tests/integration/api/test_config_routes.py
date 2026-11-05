"""Suite, target and evaluator configuration routes (017-rest-api FR-008 / API-13)."""

from __future__ import annotations


def test_suite_and_target_config_crud(client, headers_a) -> None:
    suite = client.post(
        "/v1/suites",
        headers=headers_a,
        json={"name": "Regression", "description": "Core suite", "config": {"pass_threshold": 0.9}},
    )
    assert suite.status_code == 201
    suite_body = suite.json()
    assert suite_body["name"] == "Regression"
    assert suite_body["description"] == "Core suite"
    assert suite_body["version"] == 1
    assert suite_body["config"] == {"pass_threshold": 0.9}

    target = client.post(
        "/v1/targets",
        headers=headers_a,
        json={"name": "Support model", "config": {"model": "gpt-4o-mini"}},
    )
    assert target.status_code == 201
    target_body = target.json()
    assert target_body["name"] == "Support model"
    assert target_body["version"] == 1
    assert target_body["config"] == {"model": "gpt-4o-mini"}

    suites = client.get("/v1/suites", headers=headers_a)
    assert suites.status_code == 200
    assert [item["id"] for item in suites.json()["items"]] == [suite_body["id"]]
    assert client.get(f"/v1/suites/{suite_body['id']}", headers=headers_a).json()["id"] == suite_body["id"]

    targets = client.get("/v1/targets", headers=headers_a)
    assert targets.status_code == 200
    assert [item["id"] for item in targets.json()["items"]] == [target_body["id"]]
    assert client.get(f"/v1/targets/{target_body['id']}", headers=headers_a).json()["id"] == target_body["id"]


def test_evaluator_config_create_and_get(client, headers_a) -> None:
    created = client.post(
        "/v1/evaluators",
        headers=headers_a,
        json={
            "name": "LLM judge",
            "description": "Judge config",
            "config": {"model": "gpt-4o", "temperature": 0},
        },
    )
    assert created.status_code == 201
    body = created.json()
    assert body["name"] == "LLM judge"
    assert body["description"] == "Judge config"
    assert body["version"] == "1"
    assert body["config"] == {"model": "gpt-4o", "temperature": 0}

    fetched = client.get(f"/v1/evaluators/{body['id']}", headers=headers_a)
    assert fetched.status_code == 200
    assert fetched.json()["id"] == body["id"]
    assert fetched.json()["config"] == body["config"]


def test_config_resources_are_tenant_scoped(client, headers_a, headers_b) -> None:
    suite = client.post("/v1/suites", headers=headers_a, json={"name": "Scoped suite"}).json()
    target = client.post("/v1/targets", headers=headers_a, json={"name": "Scoped target"}).json()
    evaluator = client.post("/v1/evaluators", headers=headers_a, json={"name": "Scoped evaluator"}).json()

    assert client.get("/v1/suites", headers=headers_b).json()["items"] == []
    assert client.get("/v1/targets", headers=headers_b).json()["items"] == []
    assert client.get("/v1/evaluators", headers=headers_b).json()["items"] == []

    assert client.get(f"/v1/suites/{suite['id']}", headers=headers_b).status_code == 404
    assert client.get(f"/v1/targets/{target['id']}", headers=headers_b).status_code == 404
    assert client.get(f"/v1/evaluators/{evaluator['id']}", headers=headers_b).status_code == 404


def test_config_routes_require_scopes(client, headers_none) -> None:
    assert client.get("/v1/suites", headers=headers_none).status_code == 403
    assert client.post("/v1/suites", headers=headers_none, json={"name": "denied"}).status_code == 403
    assert client.get("/v1/targets", headers=headers_none).status_code == 403
    assert client.post("/v1/targets", headers=headers_none, json={"name": "denied"}).status_code == 403
    assert client.post("/v1/evaluators", headers=headers_none, json={"name": "denied"}).status_code == 403
