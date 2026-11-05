"""Liveness/readiness helpers for the platform HTTP layer."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any, Protocol

from sqlalchemy import Engine, text

from app.core.metrics import PLATFORM_READINESS_FAILURES


class HealthCheckable(Protocol):
    def healthcheck(self) -> bool: ...


def check_database(engine: Engine) -> bool:
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
    return True


def check_redis(client: Any) -> bool:
    return bool(client.ping())


def check_storage(storage: HealthCheckable) -> bool:
    return bool(storage.healthcheck())


def liveness() -> tuple[int, dict[str, Any]]:
    return 200, {"status": "ok"}


def readiness(checks: Mapping[str, Callable[[], bool]]) -> tuple[int, dict[str, Any]]:
    results: dict[str, dict[str, Any]] = {}
    for name, check in checks.items():
        try:
            ok = bool(check())
        except Exception as exc:
            ok = False
            results[name] = {"ok": False, "error": type(exc).__name__}
        if not ok:
            PLATFORM_READINESS_FAILURES.labels(dependency=name).inc()
        results.setdefault(name, {"ok": ok})
    ready = all(result["ok"] for result in results.values())
    return (200 if ready else 503), {
        "status": "ready" if ready else "not_ready",
        "checks": results,
    }
