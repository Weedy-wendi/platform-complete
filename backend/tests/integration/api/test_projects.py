"""Project CRUD, pagination and idempotency."""

from __future__ import annotations


def test_project_crud(client, headers_a) -> None:
    created = client.post(
        "/v1/projects",
        headers=headers_a,
        json={"name": "Support Bot", "description": "First project"},
    )
    assert created.status_code == 201
    project = created.json()
    assert project["name"] == "Support Bot"
    assert project["description"] == "First project"
    assert project["id"]

    duplicate = client.post("/v1/projects", headers=headers_a, json={"name": "Support Bot"})
    assert duplicate.status_code == 409
    assert duplicate.json()["code"] == "CONFLICT"

    fetched = client.get(f"/v1/projects/{project['id']}", headers=headers_a)
    assert fetched.status_code == 200
    assert fetched.json()["id"] == project["id"]

    updated = client.patch(
        f"/v1/projects/{project['id']}",
        headers=headers_a,
        json={"name": "Support Bot v2"},
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "Support Bot v2"

    deleted = client.delete(f"/v1/projects/{project['id']}", headers=headers_a)
    assert deleted.status_code == 204
    assert client.get(f"/v1/projects/{project['id']}", headers=headers_a).status_code == 404


def test_project_list_is_paginated(client, headers_a) -> None:
    for index in range(3):
        assert client.post("/v1/projects", headers=headers_a, json={"name": f"P{index}"}).status_code == 201

    first = client.get("/v1/projects", headers=headers_a, params={"limit": 2})
    assert first.status_code == 200
    assert len(first.json()["items"]) == 2
    next_cursor = first.json()["next_cursor"]
    assert next_cursor

    second = client.get("/v1/projects", headers=headers_a, params={"limit": 2, "cursor": next_cursor})
    assert second.status_code == 200
    assert len(second.json()["items"]) == 1
    assert second.json()["next_cursor"] is None


def test_project_create_is_idempotent(client, headers_a) -> None:
    headers = {**headers_a, "Idempotency-Key": "create-project-1"}
    first = client.post("/v1/projects", headers=headers, json={"name": "Idempotent"})
    second = client.post("/v1/projects", headers=headers, json={"name": "Idempotent"})
    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] == second.json()["id"]


def test_invalid_cursor_returns_409(client, headers_a) -> None:
    response = client.get("/v1/projects", headers=headers_a, params={"cursor": "not-a-cursor"})
    assert response.status_code == 409
    assert response.json()["code"] == "INVALID_CURSOR"
