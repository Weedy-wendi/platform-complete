"""Datasource CRUD, idempotency, tenancy and scopes (017-rest-api FR-006 / API-12)."""

from __future__ import annotations


def test_datasource_crud_and_cursor_pagination(client, headers_a) -> None:
    created = client.post(
        "/v1/datasources",
        headers=headers_a,
        json={
            "name": "Warehouse",
            "description": "Primary warehouse",
            "kind": "s3",
            "config": {"bucket": "exports", "key": "samples.csv"},
        },
    )
    assert created.status_code == 201
    datasource = created.json()
    assert datasource["name"] == "Warehouse"
    assert datasource["kind"] == "s3"
    assert datasource["config"]["bucket"] == "exports"
    assert datasource["version"] == 1

    second = client.post("/v1/datasources", headers=headers_a, json={"name": "Warehouse 2"})
    assert second.status_code == 201

    first = client.get("/v1/datasources", headers=headers_a, params={"limit": 1})
    assert first.status_code == 200
    assert len(first.json()["items"]) == 1
    cursor = first.json()["next_cursor"]
    assert cursor

    rest = client.get("/v1/datasources", headers=headers_a, params={"limit": 1, "cursor": cursor})
    assert rest.status_code == 200
    assert len(rest.json()["items"]) == 1
    assert rest.json()["next_cursor"] is None

    fetched = client.get(f"/v1/datasources/{datasource['id']}", headers=headers_a)
    assert fetched.status_code == 200
    assert fetched.json()["id"] == datasource["id"]

    updated = client.patch(
        f"/v1/datasources/{datasource['id']}",
        headers=headers_a,
        json={"name": "Warehouse v2", "config": {"bucket": "exports-v2"}},
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "Warehouse v2"
    assert updated.json()["config"] == {"bucket": "exports-v2"}
    assert updated.json()["version"] == 2

    deleted = client.delete(f"/v1/datasources/{datasource['id']}", headers=headers_a)
    assert deleted.status_code == 204
    assert client.get(f"/v1/datasources/{datasource['id']}", headers=headers_a).status_code == 404


def test_datasource_create_is_idempotent(client, headers_a) -> None:
    headers = {**headers_a, "Idempotency-Key": "datasource-create-1"}
    payload = {"name": "Idempotent datasource"}
    first = client.post("/v1/datasources", headers=headers, json=payload)
    second = client.post("/v1/datasources", headers=headers, json=payload)
    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] == second.json()["id"]
    assert len(client.get("/v1/datasources", headers=headers_a).json()["items"]) == 1


def test_datasource_is_tenant_scoped(client, headers_a, headers_b) -> None:
    created = client.post("/v1/datasources", headers=headers_a, json={"name": "Tenant A source"})
    datasource_id = created.json()["id"]

    assert client.get("/v1/datasources", headers=headers_b).json()["items"] == []
    assert client.get(f"/v1/datasources/{datasource_id}", headers=headers_b).status_code == 404
    assert (
        client.patch(
            f"/v1/datasources/{datasource_id}",
            headers=headers_b,
            json={"name": "stolen"},
        ).status_code
        == 404
    )
    assert client.delete(f"/v1/datasources/{datasource_id}", headers=headers_b).status_code == 404


def test_datasource_requires_scopes(client, headers_none) -> None:
    assert client.get("/v1/datasources", headers=headers_none).status_code == 403
    assert client.post("/v1/datasources", headers=headers_none, json={"name": "denied"}).status_code == 403


def test_datasource_duplicate_name_conflicts(client, headers_a) -> None:
    assert client.post("/v1/datasources", headers=headers_a, json={"name": "Duplicate"}).status_code == 201
    duplicate = client.post("/v1/datasources", headers=headers_a, json={"name": "Duplicate"})
    assert duplicate.status_code == 409
    assert duplicate.json()["code"] == "CONFLICT"
