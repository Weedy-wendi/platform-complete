"""Graceful shutdown configuration (FR-029, T063)."""

from __future__ import annotations

import app.mcp.server as server_module


def test_run_waits_for_in_flight_requests(monkeypatch) -> None:
    captured: dict = {}

    def fake_run(app, **kwargs):
        captured["app"] = app
        captured["kwargs"] = kwargs

    monkeypatch.setattr("uvicorn.run", fake_run)
    monkeypatch.setattr(server_module, "create_app", lambda: object())

    server_module.run(host="127.0.0.1", port=9999)

    assert captured["kwargs"]["host"] == "127.0.0.1"
    assert captured["kwargs"]["port"] == 9999
    assert captured["kwargs"]["timeout_graceful_shutdown"] == 30
