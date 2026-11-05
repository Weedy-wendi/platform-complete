"""CLI dispatch tests (T075, T082)."""

from __future__ import annotations

import importlib

cli = importlib.import_module("app.cli.main")


def test_serve_uses_graceful_runner(monkeypatch) -> None:
    calls: dict = {}
    monkeypatch.setattr(cli.mcp_server, "run", lambda **kwargs: calls.update(kwargs))

    assert cli.main(["mcp", "serve", "--host", "127.0.0.1", "--port", "9999"]) == 0
    assert calls == {"host": "127.0.0.1", "port": 9999}


def test_maintain_partitions_dispatches(monkeypatch) -> None:
    import app.cli.maintain_partitions as maintenance

    calls: dict = {}

    def fake_run(**kwargs):
        calls.update(kwargs)
        return 0

    monkeypatch.setattr(maintenance, "run", fake_run)
    assert (
        cli.main(
            [
                "mcp",
                "maintain-partitions",
                "--dsn",
                "mysql+pymysql://root:pass@db/pingce",
                "--months-ahead",
                "2",
                "--retention-days",
                "30",
                "--dry-run",
            ]
        )
        == 0
    )
    assert calls == {
        "dsn": "mysql+pymysql://root:pass@db/pingce",
        "months_ahead": 2,
        "retention_days": 30,
        "dry_run": True,
    }
