"""Fixtures for REST API integration tests."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.api import ApiServices, build_api_services, create_api_app
from app.core.context import Principal
from app.core.errors import UnauthorizedError
from app.modules.audit.public import AuditLogEvent
from app.modules.identity.public import ApiKeyAuthenticator

TENANT_A = "tenant-a"
TENANT_B = "tenant-b"

READ_SCOPES = frozenset(
    {
        "projects:read",
        "datasets:read",
        "datasources:read",
        "runs:read",
        "evaluators:read",
        "gate:read",
        "reports:read",
        "badcases:read",
        "functional:read",
    }
)
WRITE_SCOPES = frozenset(
    {
        "projects:write",
        "datasets:write",
        "datasources:write",
        "runs:write",
        "evaluators:write",
        "functional:write",
    }
)
ALL_SCOPES = READ_SCOPES | WRITE_SCOPES

KEY_A = "pk_test_tenant_a_secret"
KEY_B = "pk_test_tenant_b_secret"
KEY_ADMIN = "pk_test_admin_secret"
KEY_NONE = "pk_test_no_scope_secret"


class FakeVerifier:
    def __init__(self, principals: dict[str, Principal]) -> None:
        self._principals = principals

    def verify(self, raw_key: str) -> Principal:
        principal = self._principals.get(raw_key)
        if principal is None:
            raise UnauthorizedError("Invalid API key")
        return principal


@pytest.fixture()
def principals() -> dict[str, Principal]:
    return {
        KEY_A: Principal(
            tenant_id=TENANT_A,
            subject="api_key:tenant-a",
            scopes=ALL_SCOPES,
            api_key_id=1,
        ),
        KEY_B: Principal(
            tenant_id=TENANT_B,
            subject="api_key:tenant-b",
            scopes=ALL_SCOPES,
            api_key_id=2,
        ),
        KEY_ADMIN: Principal(
            tenant_id=TENANT_A,
            subject="api_key:admin",
            scopes=frozenset({"platform:admin"}),
            api_key_id=3,
        ),
        KEY_NONE: Principal(
            tenant_id=TENANT_A,
            subject="api_key:none",
            scopes=frozenset(),
            api_key_id=4,
        ),
    }


class RecordingAuditLogWriter:
    def __init__(self) -> None:
        self.events: list[AuditLogEvent] = []

    def write(self, event: AuditLogEvent) -> None:
        self.events.append(event)


@pytest.fixture()
def api_services() -> ApiServices:
    return build_api_services()


@pytest.fixture()
def audit_writer() -> RecordingAuditLogWriter:
    return RecordingAuditLogWriter()


@pytest.fixture()
def app(principals: dict[str, Principal], api_services: ApiServices):
    return create_api_app(
        services=api_services,
        authenticator=ApiKeyAuthenticator(FakeVerifier(principals)),
        ready_checks={"database": lambda: True},
        cursor_secret="test-api-cursor",
    )


@pytest.fixture()
def audited_app(
    principals: dict[str, Principal],
    api_services: ApiServices,
    audit_writer: RecordingAuditLogWriter,
):
    return create_api_app(
        services=api_services,
        authenticator=ApiKeyAuthenticator(FakeVerifier(principals)),
        ready_checks={"database": lambda: True},
        cursor_secret="test-api-cursor",
        audit_writer=audit_writer,
    )


@pytest.fixture()
def client(app) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def audited_client(audited_app) -> Iterator[TestClient]:
    with TestClient(audited_app) as test_client:
        yield test_client


def _headers(raw_key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {raw_key}"}


@pytest.fixture()
def headers_a() -> dict[str, str]:
    return _headers(KEY_A)


@pytest.fixture()
def headers_b() -> dict[str, str]:
    return _headers(KEY_B)


@pytest.fixture()
def headers_admin() -> dict[str, str]:
    return _headers(KEY_ADMIN)


@pytest.fixture()
def headers_none() -> dict[str, str]:
    return _headers(KEY_NONE)
