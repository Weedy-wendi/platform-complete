"""Write-path audit trail for mutating REST requests (017-rest-api FR-015)."""

from __future__ import annotations

from dataclasses import replace

from fastapi.testclient import TestClient

from app.api import ApiServices, create_api_app
from app.modules.identity.public import ApiKeyAuthenticator
from tests.integration.api.conftest import (
    KEY_A,
    KEY_NONE,
    FakeVerifier,
    RecordingAuditLogWriter,
)


def test_post_writes_exactly_one_audit_record(
    audited_client: TestClient,
    audit_writer: RecordingAuditLogWriter,
    headers_a: dict[str, str],
) -> None:
    response = audited_client.post(
        "/v1/projects",
        headers={**headers_a, "X-Trace-Id": "trace-audit-post"},
        json={"name": "Audited project", "description": "body-secret-marker"},
    )
    assert response.status_code == 201
    assert response.headers["x-trace-id"] == "trace-audit-post"
    assert len(audit_writer.events) == 1

    event = audit_writer.events[0]
    assert event.tenant_id == "tenant-a"
    assert event.actor_id == "api_key:tenant-a"
    assert event.action == "POST /v1/projects"
    assert event.resource_type == "http_route"
    assert event.resource_id == "/v1/projects"
    assert event.trace_id == "trace-audit-post"
    assert event.status == "success"
    assert event.detail == {"status_code": 201, "method": "POST"}

    rendered = repr(event)
    assert KEY_A not in rendered
    assert "body-secret-marker" not in rendered
    assert "Authorization" not in rendered


def test_get_writes_no_audit_record(
    audited_client: TestClient,
    audit_writer: RecordingAuditLogWriter,
    headers_a: dict[str, str],
) -> None:
    assert audited_client.get("/v1/projects", headers=headers_a).status_code == 200
    assert audited_client.get("/healthz").status_code == 200
    assert audit_writer.events == []


def test_denied_write_records_attempt_without_secrets(
    audited_client: TestClient,
    audit_writer: RecordingAuditLogWriter,
    headers_none: dict[str, str],
) -> None:
    response = audited_client.post(
        "/v1/projects",
        headers=headers_none,
        json={"name": "Denied project", "description": "body-secret-marker"},
    )
    assert response.status_code == 403
    assert len(audit_writer.events) == 1

    event = audit_writer.events[0]
    assert event.tenant_id == "tenant-a"
    assert event.actor_id == "api_key:none"
    assert event.action == "POST /v1/projects"
    assert event.status == "denied"
    assert event.detail["status_code"] == 403

    rendered = repr(event)
    assert KEY_NONE not in rendered
    assert "body-secret-marker" not in rendered


def test_unauthenticated_write_records_anonymous_attempt(
    audited_client: TestClient,
    audit_writer: RecordingAuditLogWriter,
) -> None:
    response = audited_client.post(
        "/v1/projects",
        headers={"Authorization": "Bearer pk_test_unknown_secret"},
        json={"name": "Unauthenticated"},
    )
    assert response.status_code == 401
    assert len(audit_writer.events) == 1

    event = audit_writer.events[0]
    assert event.tenant_id == "unknown"
    assert event.actor_id == "anonymous"
    assert event.status == "denied"
    assert "pk_test_unknown_secret" not in repr(event)


def test_no_writer_means_no_crash(client: TestClient, headers_a: dict[str, str]) -> None:
    response = client.post("/v1/projects", headers=headers_a, json={"name": "No audit writer"})
    assert response.status_code == 201


def test_audit_writer_can_be_configured_on_api_services(
    principals,
    api_services: ApiServices,
    audit_writer: RecordingAuditLogWriter,
    headers_a: dict[str, str],
) -> None:
    services = replace(api_services, audit_writer=audit_writer)
    app = create_api_app(
        services=services,
        authenticator=ApiKeyAuthenticator(FakeVerifier(principals)),
        ready_checks={"database": lambda: True},
        cursor_secret="test-api-cursor",
    )
    with TestClient(app) as client:
        assert client.post("/v1/projects", headers=headers_a, json={"name": "Via services"}).status_code == 201

    assert len(audit_writer.events) == 1
    assert audit_writer.events[0].action == "POST /v1/projects"
