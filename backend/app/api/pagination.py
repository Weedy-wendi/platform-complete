"""Opaque, signed cursor pagination for the REST adapter.

The contract forbids offset pagination. Cursors carry the last stable sort key
and are bound to tenant, route and query fingerprint, so a cursor cannot be
replayed against another tenant or a different filter.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from collections.abc import Callable, Sequence
from typing import Any

from app.core.errors import InvalidCursorError
from app.core.pagination import Page

_DEFAULT_SECRET = "dev-cursor-change-me"


def _b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def query_fingerprint(params: dict[str, Any]) -> str:
    canonical = json.dumps(params, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class CursorCodec:
    def __init__(self, secret: str | None = None, *, ttl_seconds: int = 900) -> None:
        self._secret = (secret or os.environ.get("PINGCE_API_CURSOR_SECRET") or _DEFAULT_SECRET).encode("utf-8")
        self._ttl_seconds = ttl_seconds

    def _sign(self, payload: bytes) -> str:
        return _b64encode(hmac.new(self._secret, payload, hashlib.sha256).digest())

    def encode(self, *, tenant_id: str, route: str, query_hash: str, last_key: str) -> str:
        payload = {
            "v": 1,
            "t": tenant_id,
            "route": route,
            "q": query_hash,
            "k": last_key,
            "exp": int(time.time()) + self._ttl_seconds,
        }
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return f"{_b64encode(raw)}.{self._sign(raw)}"

    def decode(self, cursor: str, *, tenant_id: str, route: str, query_hash: str) -> str:
        try:
            body, signature = cursor.split(".", 1)
            raw = _b64decode(body)
            if not hmac.compare_digest(self._sign(raw), signature):
                raise InvalidCursorError()
            payload = json.loads(raw)
        except InvalidCursorError:
            raise
        except Exception as exc:
            raise InvalidCursorError() from exc

        if payload.get("v") != 1:
            raise InvalidCursorError()
        if payload.get("t") != tenant_id or payload.get("route") != route or payload.get("q") != query_hash:
            raise InvalidCursorError()
        if int(payload.get("exp", 0)) < int(time.time()):
            raise InvalidCursorError()
        return str(payload.get("k", ""))


def page_records[T](
    records: Sequence[T],
    *,
    limit: int,
    cursor: str | None,
    codec: CursorCodec,
    tenant_id: str,
    route: str,
    query_hash: str,
    key_fn: Callable[[T], str],
    reverse: bool = False,
) -> Page[T]:
    """Return a keyset page from already-filtered records.

    ``records`` are sorted by ``key_fn`` (descending when ``reverse`` is true).
    """

    rows = sorted(records, key=key_fn, reverse=reverse)
    if cursor:
        last_key = codec.decode(cursor, tenant_id=tenant_id, route=route, query_hash=query_hash)
        if reverse:
            rows = [row for row in rows if key_fn(row) < last_key]
        else:
            rows = [row for row in rows if key_fn(row) > last_key]

    items = list(rows[:limit])
    next_cursor = None
    if len(rows) > limit and items:
        next_cursor = codec.encode(
            tenant_id=tenant_id,
            route=route,
            query_hash=query_hash,
            last_key=key_fn(items[-1]),
        )
    return Page(items=items, next_cursor=next_cursor, truncated=len(rows) > limit)


__all__ = ["CursorCodec", "page_records", "query_fingerprint"]
