"""Dataset creation, immutable versions and sample paging."""

from __future__ import annotations


def _create_project(client, headers, name: str = "Dataset project") -> str:
    response = client.post("/v1/projects", headers=headers, json={"name": name})
    assert response.status_code == 201
    return response.json()["id"]


def test_dataset_crud_and_sample_paging(client, headers_a) -> None:
    project_id = _create_project(client, headers_a)

    created = client.post(
        "/v1/datasets",
        headers=headers_a,
        json={"project_id": project_id, "name": "Support QA", "tags": ["support"]},
    )
    assert created.status_code == 201
    dataset = created.json()
    assert dataset["project_id"] == project_id
    assert dataset["latest_version"] == 0
    assert dataset["tags"] == ["support"]

    duplicate = client.post(
        "/v1/datasets",
        headers=headers_a,
        json={"project_id": project_id, "name": "Support QA"},
    )
    assert duplicate.status_code == 409

    listed = client.get("/v1/datasets", headers=headers_a, params={"query": "support"})
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()["items"]] == [dataset["id"]]

    version = client.post(
        f"/v1/datasets/{dataset['id']}/versions",
        headers=headers_a,
        json={
            "schema": {"fields": [{"name": "question", "type": "string"}]},
            "content_hash": "sha256-v1",
            "samples": [
                {"sample_key": "s1", "payload": {"question": "one"}},
                {"sample_key": "s2", "payload": {"question": "two"}},
            ],
        },
    )
    assert version.status_code == 201
    assert version.json()["version"] == 1
    assert version.json()["row_count"] == 2
    assert version.json()["content_hash"] == "sha256-v1"

    repeated = client.post(
        f"/v1/datasets/{dataset['id']}/versions",
        headers=headers_a,
        json={"schema": {}, "content_hash": "sha256-v1"},
    )
    assert repeated.status_code == 201
    assert repeated.json()["version"] == 1

    first_page = client.get(
        f"/v1/datasets/{dataset['id']}/versions/1/samples",
        headers=headers_a,
        params={"limit": 1},
    )
    assert first_page.status_code == 200
    assert [item["sample_id"] for item in first_page.json()["items"]] == ["s1"]
    assert first_page.json()["next_cursor"]

    second_page = client.get(
        f"/v1/datasets/{dataset['id']}/versions/1/samples",
        headers=headers_a,
        params={"limit": 1, "cursor": first_page.json()["next_cursor"]},
    )
    assert [item["sample_id"] for item in second_page.json()["items"]] == ["s2"]


def test_dataset_is_tenant_scoped(client, headers_a, headers_b) -> None:
    project_id = _create_project(client, headers_a, name="Scoped project")
    created = client.post(
        "/v1/datasets",
        headers=headers_a,
        json={"project_id": project_id, "name": "Scoped dataset"},
    )
    dataset_id = created.json()["id"]

    assert client.get("/v1/datasets", headers=headers_b).json()["items"] == []
    missing = client.get(
        f"/v1/datasets/{dataset_id}/versions/1/samples",
        headers=headers_b,
    )
    assert missing.status_code == 404


def test_publish_requires_existing_dataset(client, headers_a) -> None:
    response = client.post(
        "/v1/datasets/missing/versions",
        headers=headers_a,
        json={"schema": {}, "content_hash": "hash"},
    )
    assert response.status_code == 404
