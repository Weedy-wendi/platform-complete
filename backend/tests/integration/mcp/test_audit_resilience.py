"""Audit write failures must never block a tool call (FR-022, T056)."""

from __future__ import annotations

from starlette.testclient import TestClient

from app.core.context import Principal
from app.mcp.audit import McpAuditService
from app.mcp.server import create_app
from app.modules.audit.public import AuditEvent


class FailingWriter:
    def write(self, event: AuditEvent) -> None:
        raise RuntimeError("audit database is down")


def _principal() -> Principal:
    return Principal(tenant_id="tenant-a", subject="user:1", client_id="key-1", api_key_id=1)


def test_record_swallows_writer_failures() -> None:
    service = McpAuditService(FailingWriter())
    service.record(
        principal=_principal(),
        tool_name="list_projects",
        tool_version="1.0.0",
        status="ok",
        latency_ms=1,
        result_bytes=2,
        trace_id="trace",
    )


def test_tool_call_succeeds_when_audit_write_fails(settings, api_key_service) -> None:
    app = create_app(
        settings,
        api_key_service=api_key_service,
        audit_writer=FailingWriter(),
    )
    issued = api_key_service.issue(
        tenant_id="tenant-a",
        name="audit-failure",
        scopes={"mcp:projects:read"},
    )
    headers = {
        "Authorization": f"Bearer {issued.raw_key}",
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
    }
    with TestClient(app) as client:
        response = client.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "list_projects", "arguments": {}},
            },
            headers=headers,
        )
    assert response.status_code == 200
    assert response.json()["result"]["isError"] is False
