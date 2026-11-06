"""OpenAPI 3.1 export and request size limits."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.api import create_api_app
from app.modules.identity.public import ApiKeyAuthenticator
from tests.integration.api.conftest import KEY_A, FakeVerifier


def test_session_factory_wires_identity_authenticator() -> None:
    app = create_api_app(session_factory=sessionmaker(), api_key_pepper="test-pepper")
    assert isinstance(app.state.authenticator, ApiKeyAuthenticator)


def test_openapi_export_is_31_and_complete(client) -> None:
    response = client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    assert schema["openapi"] == "3.1.0"
    assert schema["info"]["version"] == "1.0.0"
    assert schema["components"]["securitySchemes"]["bearerAuth"]["scheme"] == "bearer"
    assert schema["security"] == [{"bearerAuth": []}]

    paths = schema["paths"]
    for path in (
        "/healthz",
        "/readyz",
        "/v1/projects",
        "/v1/datasets",
        "/v1/runs",
        "/v1/evaluators",
        "/v1/gates/{suite_id}/{run_id}",
        "/v1/reports/{run_id}",
        "/v1/badcases/search",
        "/v1/admin/tenants",
    ):
        assert path in paths

    # Health endpoints are explicitly public.
    assert schema["paths"]["/healthz"]["get"]["security"] == []


def test_openapi_is_also_exported_under_v1(client) -> None:
    response = client.get("/v1/openapi.json")
    assert response.status_code == 200
    assert response.json()["openapi"] == "3.1.0"


def test_request_body_limit(principals) -> None:
    app = create_api_app(
        authenticator=ApiKeyAuthenticator(FakeVerifier(principals)),
        max_request_bytes=64,
    )
    with TestClient(app) as limited:
        response = limited.post(
            "/v1/projects",
            headers={"Authorization": f"Bearer {KEY_A}"},
            json={"name": "x" * 200},
        )
    assert response.status_code == 413
    body = response.json()
    assert body["code"] == "REQUEST_TOO_LARGE"
    assert body["details"]["limit"] == 64
    assert body["trace_id"]
