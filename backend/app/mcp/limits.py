"""Result-size limits, truncation and redaction."""

from __future__ import annotations

import json
import re
from typing import Any

from app.core.errors import ResultTooLargeError

MAX_RESULT_BYTES = 65536
MAX_STRING_BYTES = 4096

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_PHONE = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
_SECRET = re.compile(r"(?i)(sk|pk)_[A-Za-z0-9._~-]{8,}")


def truncate_utf8(value: str, max_bytes: int = MAX_STRING_BYTES) -> str:
    encoded = value.encode("utf-8")
    if len(encoded) <= max_bytes:
        return value
    ellipsis = "…"
    budget = max(0, max_bytes - len(ellipsis.encode("utf-8")))
    truncated = encoded[:budget].decode("utf-8", errors="ignore")
    return truncated + ellipsis


def redact_text(value: str) -> str:
    value = _EMAIL.sub("[EMAIL]", value)
    value = _PHONE.sub("[PHONE]", value)
    value = _SECRET.sub("[SECRET]", value)
    return value


def redact_mapping(value: Any) -> Any:
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, list):
        return [redact_mapping(item) for item in value]
    if isinstance(value, dict):
        sensitive = {"authorization", "api_key", "apikey", "secret", "password", "token"}
        result: dict[str, Any] = {}
        for key, item in value.items():
            if key.lower() in sensitive:
                result[key] = "[REDACTED]"
            else:
                result[key] = redact_mapping(item)
        return result
    return value


def size_bytes(value: Any) -> int:
    return len(json.dumps(value, ensure_ascii=False, default=str).encode("utf-8"))


def _truncate_strings(value: Any, budget: int) -> Any:
    if isinstance(value, str):
        return truncate_utf8(value, max_bytes=budget)
    if isinstance(value, list):
        return [_truncate_strings(item, budget) for item in value]
    if isinstance(value, dict):
        return {key: _truncate_strings(item, budget) for key, item in value.items()}
    return value


def fit_mapping(value: dict[str, Any], *, max_bytes: int = MAX_STRING_BYTES) -> tuple[dict[str, Any], bool]:
    """Shrink a single sample/IO payload until it fits ``max_bytes``.

    Returns ``(payload, changed)``. Structural shape is preserved; string leaves
    are shortened first. As a last resort the payload is replaced by a marker so
    a single record can never exceed the per-record limit.
    """
    if size_bytes(value) <= max_bytes:
        return value, False
    budget = max_bytes // 2
    current: Any = value
    while budget >= 1:
        current = _truncate_strings(value, budget)
        if size_bytes(current) <= max_bytes:
            return current, True
        budget //= 2
    return {"_truncated": True}, True


def cap_result(value: Any, *, max_bytes: int = MAX_RESULT_BYTES) -> tuple[Any, bool]:
    """Truncate list-style results until they fit.

    Returns ``(value, truncated)``. Scalar/object results that cannot be reduced
    raise ``ResultTooLargeError`` so callers can return a stable error code.
    """
    if size_bytes(value) <= max_bytes:
        return value, False

    if isinstance(value, dict) and isinstance(value.get("items"), list):
        items = list(value["items"])
        while items and size_bytes({**value, "items": items, "truncated": True}) > max_bytes:
            items.pop()
        if items:
            return {**value, "items": items, "truncated": True}, True
        raise ResultTooLargeError()

    if isinstance(value, dict):
        reduced = {key: truncate_utf8(item) if isinstance(item, str) else item for key, item in value.items()}
        if size_bytes(reduced) <= max_bytes:
            return reduced, True
    raise ResultTooLargeError()
