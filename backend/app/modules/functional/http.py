"""HTTP execution adapter with lazy httpx import (FUN-02)."""

from __future__ import annotations

import time
from typing import Any

from app.core.errors import UpstreamUnavailableError
from app.modules.functional.public import HttpRequestSpec, HttpResponse


class HttpxExecutor:
    """Production HTTP executor; tests inject a fake executor."""

    def __init__(self, client: Any | None = None) -> None:
        self._client = client

    def _client_or_raise(self) -> Any:
        if self._client is not None:
            return self._client
        try:
            import httpx
        except ImportError as exc:  # pragma: no cover - dev dependency
            raise UpstreamUnavailableError("httpx is required for API test steps") from exc
        self._client = httpx.Client()
        return self._client

    def execute(self, request: HttpRequestSpec) -> HttpResponse:
        client = self._client_or_raise()
        started = time.perf_counter()
        try:
            response = client.request(
                request.method,
                request.url,
                headers=request.headers,
                json=request.json,
                timeout=request.timeout_seconds,
            )
        except Exception as exc:  # noqa: BLE001 - mapped into a test failure
            raise UpstreamUnavailableError("HTTP step failed") from exc
        duration_ms = int((time.perf_counter() - started) * 1000)
        try:
            body: Any = response.json()
        except ValueError:
            body = response.text
        return HttpResponse(
            status_code=int(response.status_code),
            body=body,
            duration_ms=duration_ms,
            headers=dict(getattr(response, "headers", {}) or {}),
        )


__all__ = ["HttpxExecutor"]
