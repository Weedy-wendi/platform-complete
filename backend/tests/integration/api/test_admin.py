"""Administration surface: tenants, users, roles, keys and providers."""

from __future__ import annotations


def test_admin_requires_platform_admin(client, headers_none) -> None:
    response = client.get("/v1/admin/tenants", headers=headers_none)
    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"


def test_tenant_lifecycle(client, headers_admin) -> None:
    created = client.post(
        "/v1/admin/tenants",
        headers=headers_admin,
        json={"name": "Acme", "slug": "acme"},
    )
    assert created.status_code == 201
    tenant = created.json()
    assert tenant["status"] == "active"

    duplicate = client.post(
        "/v1/admin/tenants",
        headers=headers_admin,
        json={"name": "Acme 2", "slug": "acme"},
    )
    assert duplicate.status_code == 409

    listed = client.get("/v1/admin/tenants", headers=headers_admin)
    assert [item["id"] for item in listed.json()["items"]] == [tenant["id"]]

    fetched = client.get(f"/v1/admin/tenants/{tenant['id']}", headers=headers_admin)
    assert fetched.status_code == 200

    disabled = client.put(
        f"/v1/admin/tenants/{tenant['id']}/status",
        headers=headers_admin,
        json={"status": "disabled"},
    )
    assert disabled.status_code == 200
    assert disabled.json()["status"] == "disabled"


def test_user_role_and_api_key_lifecycle(client, headers_admin) -> None:
    created = client.post(
        "/v1/admin/users",
        headers=headers_admin,
        json={"email": "alice@example.com", "roles": ["viewer"]},
    )
    assert created.status_code == 201
    user = created.json()
    assert user["email"] == "alice@example.com"

    listed = client.get("/v1/admin/users", headers=headers_admin)
    assert [item["id"] for item in listed.json()["items"]] == [user["id"]]

    assert client.delete(f"/v1/admin/users/{user['id']}", headers=headers_admin).status_code == 204
    assert client.get(f"/v1/admin/users/{user['id']}", headers=headers_admin).json()["status"] == "disabled"

    role = client.post(
        "/v1/admin/roles",
        headers=headers_admin,
        json={"name": "viewer", "permissions": ["identity:user:read"]},
    )
    assert role.status_code == 201
    assert client.get("/v1/admin/roles", headers=headers_admin).json()["items"][0]["name"] == "viewer"

    issued = client.post(
        "/v1/admin/api-keys",
        headers=headers_admin,
        json={"name": "ci", "scopes": ["projects:read"]},
    )
    assert issued.status_code == 201
    key = issued.json()
    assert key["raw_key"].startswith("pk_")

    rotated = client.post(f"/v1/admin/api-keys/{key['key_id']}/rotate", headers=headers_admin)
    assert rotated.status_code == 201
    assert rotated.json()["key_id"] != key["key_id"]

    assert client.delete(f"/v1/admin/api-keys/{rotated.json()['key_id']}", headers=headers_admin).status_code == 204
    assert client.get("/v1/admin/providers", headers=headers_admin).status_code == 200
