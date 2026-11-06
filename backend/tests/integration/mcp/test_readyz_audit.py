"""Readiness must include the audit database (T080)."""

from __future__ import annotations

from starlette.testclient import TestClient

from app.mcp.server import create_app
from app.modules.audit.public import InMemoryAuditWriter


class BrokenEngine:
    def connect(self):
        raise RuntimeError("audit database is down")


def test_readyz_reports_audit_database_failure(settings, api_key_service) -> None:
    app = create_app(
        settings,
        api_key_service=api_key_service,
        audit_writer=InMemoryAuditWriter(),
    )
    app.state.audit_engine = BrokenEngine()
    with TestClient(app) as client:
        response = client.get("/readyz")
    assert response.status_code == 503
    assert response.json()["dependency"] == "mysql-audit"
