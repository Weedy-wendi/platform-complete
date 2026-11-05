"""Opaque, signed pagination cursors."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any, NoReturn

from app.core.errors import InvalidCursorError
from app.core.metrics import MCP_CURSOR_INVALID


def _b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def query_fingerprint(params: dict[str, Any]) -> str:
    canonical = json.dumps(params, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _invalid() -> NoReturn:
    MCP_CURSOR_INVALID.inc()
    raise InvalidCursorError()


class CursorCodec:
    def __init__(self, secret: str, *, ttl_seconds: int = 900) -> None:
        if not secret:
            raise ValueError("cursor secret is required")
        self._secret = secret.encode("utf-8")
        self._ttl_seconds = ttl_seconds

    def _sign(self, payload: bytes) -> str:
        signature = hmac.new(self._secret, payload, hashlib.sha256).digest()
        return _b64encode(signature)

    def encode(
        self,
        *,
        tenant_id: str,
        tool: str,
        query_hash: str,
        last_key: dict[str, Any] | str | int | list[Any],
    ) -> str:
        payload = {
            "v": 1,
            "t": tenant_id,
            "tool": tool,
            "q": query_hash,
            "k": last_key,
            "exp": int(time.time()) + self._ttl_seconds,
        }
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
        return f"{_b64encode(raw)}.{self._sign(raw)}"

    def decode(self, cursor: str, *, tenant_id: str, tool: str, query_hash: str) -> dict[str, Any]:
        try:
            body, signature = cursor.split(".", 1)
            raw = _b64decode(body)
            expected = self._sign(raw)
            if not hmac.compare_digest(expected, signature):
                _invalid()
            payload = json.loads(raw)
        except InvalidCursorError:
            raise
        except Exception as exc:
            MCP_CURSOR_INVALID.inc()
            raise InvalidCursorError() from exc

        if payload.get("v") != 1:
            _invalid()
        if payload.get("t") != tenant_id or payload.get("tool") != tool or payload.get("q") != query_hash:
            _invalid()
        if int(payload.get("exp", 0)) < int(time.time()):
            _invalid()
        return payload
