"""Health, metrics and generic error envelope tests."""

from __future__ import annotations


def test_healthz_is_public(client) -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readyz_reports_ready(client) -> None:
    response = client.get("/readyz")
    assert response.status_code == 200
    assert response.json()["status"] == "ready"
    assert response.json()["checks"] == {"database": {"ok": True}}


def test_metrics_are_prometheus_text(client) -> None:
    response = client.get("/metrics")
    assert response.status_code == 200
    assert "text/plain" in response.headers["content-type"]
    assert "http_requests_total" in response.text


def test_unknown_route_uses_error_envelope(client) -> None:
    response = client.get("/v1/does-not-exist")
    assert response.status_code == 404
    body = response.json()
    assert body["code"] == "NOT_FOUND"
    assert body["trace_id"]
    assert "trace_id" in body
    assert "detail" not in body


def test_trace_id_is_propagated(client) -> None:
    response = client.get("/v1/projects", headers={"X-Trace-Id": "trace-client-1"})
    assert response.status_code == 401
    assert response.json()["trace_id"] == "trace-client-1"
    assert response.headers["x-trace-id"] == "trace-client-1"
