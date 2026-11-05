"""Authentication, authorization, tenancy and error-shape tests."""

from __future__ import annotations


def test_missing_credentials_returns_401(client) -> None:
    response = client.get("/v1/projects")
    assert response.status_code == 401
    assert response.headers["www-authenticate"].startswith("Bearer")
    body = response.json()
    assert body["code"] == "UNAUTHORIZED"
    assert body["message"]
    assert body["trace_id"]
    assert body["details"]["retryable"] is False


def test_invalid_key_returns_401(client) -> None:
    response = client.get("/v1/projects", headers={"Authorization": "Bearer pk_test_unknown"})
    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHORIZED"


def test_missing_scope_returns_403(client, headers_none) -> None:
    response = client.get("/v1/projects", headers=headers_none)
    assert response.status_code == 403
    body = response.json()
    assert body["code"] == "FORBIDDEN"
    assert body["trace_id"]
    assert body["details"]["required_scope"] == "projects:read"


def test_cross_tenant_project_is_hidden(client, headers_a, headers_b) -> None:
    created = client.post("/v1/projects", headers=headers_a, json={"name": "Tenant A project"})
    assert created.status_code == 201
    project_id = created.json()["id"]

    list_a = client.get("/v1/projects", headers=headers_a)
    assert [item["id"] for item in list_a.json()["items"]] == [project_id]

    list_b = client.get("/v1/projects", headers=headers_b)
    assert list_b.status_code == 200
    assert list_b.json()["items"] == []

    read_b = client.get(f"/v1/projects/{project_id}", headers=headers_b)
    assert read_b.status_code == 404
    assert read_b.json()["code"] == "NOT_FOUND"


def test_validation_error_shape(client, headers_a) -> None:
    response = client.post("/v1/projects", headers=headers_a, json={"description": "missing name"})
    assert response.status_code == 400
    body = response.json()
    assert body["code"] == "VALIDATION_ERROR"
    assert body["trace_id"]
    assert body["details"]["errors"][0]["loc"] == ["body", "name"]


def test_identity_me_returns_principal(client, headers_a) -> None:
    response = client.get("/v1/identity/me", headers=headers_a)
    assert response.status_code == 200
    body = response.json()
    assert body["tenant_id"] == "tenant-a"
    assert body["subject_id"] == "api_key:tenant-a"
    assert "projects:read" in body["scopes"]
