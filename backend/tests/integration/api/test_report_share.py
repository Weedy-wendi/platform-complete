"""Signed report share links (017-rest-api API-14)."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.api import create_api_app
from app.api.services import ApiServices
from app.modules.identity.public import ApiKeyAuthenticator
from tests.integration.api.conftest import FakeVerifier

SHARE_SECRET = "test-report-share-secret"


@pytest.fixture()
def share_client(principals, api_services: ApiServices) -> Iterator[TestClient]:
    app = create_api_app(
        services=api_services,
        authenticator=ApiKeyAuthenticator(FakeVerifier(principals)),
        ready_checks={"database": lambda: True},
        cursor_secret="test-api-cursor",
        report_share_secret=SHARE_SECRET,
    )
    with TestClient(app) as client:
        yield client


def _create_run(client: TestClient, headers: dict[str, str]) -> str:
    response = client.post(
        "/v1/runs",
        headers=headers,
        json={"suite_id": "suite-1", "dataset_id": "dataset-1", "dataset_version": 1},
    )
    assert response.status_code == 202
    return response.json()["run_id"]


def _forge_token(*, tenant_id: str, run_id: str, expires_at: int, secret: str = SHARE_SECRET) -> str:
    payload = {
        "tenant_id": tenant_id,
        "run_id": run_id,
        "format": "json",
        "expires_at": expires_at,
    }
    encoded = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode()
    signature = hmac.new(secret.encode(), encoded.encode(), hashlib.sha256).hexdigest()[:32]
    return f"{encoded}.{signature}"


def test_report_share_link_can_be_created_and_read(share_client, headers_a) -> None:
    run_id = _create_run(share_client, headers_a)

    created = share_client.post(
        f"/v1/reports/{run_id}/share",
        headers=headers_a,
        json={"ttl_seconds": 600},
    )
    assert created.status_code == 200
    body = created.json()
    assert body["token"]
    assert body["url"] == f"/v1/share/{body['token']}"
    assert body["expires_at"]

    shared = share_client.get(body["url"], headers=headers_a)
    assert shared.status_code == 200
    report = shared.json()
    assert report["run_id"] == run_id
    assert report["manifest_hash"]


def test_expired_share_token_is_rejected(share_client, headers_a) -> None:
    run_id = _create_run(share_client, headers_a)
    token = _forge_token(tenant_id="tenant-a", run_id=run_id, expires_at=int(time.time()) - 10)
    response = share_client.get(f"/v1/share/{token}", headers=headers_a)
    assert response.status_code == 400
    assert response.json()["code"] == "INVALID_ARGUMENT"


def test_tampered_share_token_is_rejected(share_client, headers_a) -> None:
    run_id = _create_run(share_client, headers_a)
    token = _forge_token(tenant_id="tenant-a", run_id=run_id, expires_at=int(time.time()) + 600)
    tampered = token.rsplit(".", 1)[0] + "." + ("0" * 32)
    response = share_client.get(f"/v1/share/{tampered}", headers=headers_a)
    assert response.status_code == 400
    assert response.json()["code"] == "INVALID_ARGUMENT"


def test_cross_tenant_share_token_returns_404(share_client, headers_a, headers_b) -> None:
    run_id = _create_run(share_client, headers_a)
    created = share_client.post(f"/v1/reports/{run_id}/share", headers=headers_a, json={})
    token = created.json()["token"]

    response = share_client.get(f"/v1/share/{token}", headers=headers_b)
    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"


def test_share_creation_requires_reports_scope(share_client, headers_none) -> None:
    response = share_client.post("/v1/reports/run-x/share", headers=headers_none, json={})
    assert response.status_code == 403


def test_share_secret_can_be_injected_and_env_is_supported(monkeypatch, principals) -> None:
    monkeypatch.setenv("PINGCE_REPORT_SHARE_SECRET", "env-secret")
    app = create_api_app(
        authenticator=ApiKeyAuthenticator(FakeVerifier(principals)),
        ready_checks={"database": lambda: True},
    )
    assert app.state.report_share_secret == "env-secret"


def test_share_tokens_are_bound_to_the_configured_secret(share_client, headers_a) -> None:
    run_id = _create_run(share_client, headers_a)
    token = _forge_token(
        tenant_id="tenant-a",
        run_id=run_id,
        expires_at=int(time.time()) + 600,
        secret="wrong-secret",
    )
    assert share_client.get(f"/v1/share/{token}", headers=headers_a).status_code == 400
