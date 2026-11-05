"""Evidence adapter: artifact ids only, never blobs in MySQL (FUN-05)."""

from __future__ import annotations

from typing import Any

from app.core.ids import new_ulid
from app.core.logging import redact_text

_SENSITIVE_KEYS = frozenset(
    {
        "password",
        "passwd",
        "secret",
        "token",
        "api_key",
        "apikey",
        "authorization",
        "cookie",
        "set-cookie",
        "access_token",
        "refresh_token",
        "private_key",
        "session",
        "session_id",
        "csrf",
        "csrf_token",
    }
)
_REDACTED = "[REDACTED]"


def _is_sensitive(key: str) -> bool:
    lowered = key.lower()
    return (
        lowered in _SENSITIVE_KEYS
        or lowered.endswith("_token")
        or lowered.endswith("_secret")
        or lowered.endswith("_password")
        or lowered.endswith("_key")
    )


def sanitize_evidence(value: Any) -> Any:
    """Recursively drop credentials and redact token-like text from evidence."""

    if isinstance(value, dict):
        return {key: _REDACTED if _is_sensitive(str(key)) else sanitize_evidence(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [sanitize_evidence(item) for item in value]
    if isinstance(value, bytes):
        return value
    if isinstance(value, str):
        return redact_text(value)
    return value


class InMemoryEvidenceWriter:
    """Small in-process evidence sink for tests and local runs."""

    def __init__(self) -> None:
        self._items: dict[str, tuple[str, str, bytes | str | dict[str, Any]]] = {}

    def put(
        self,
        *,
        tenant_id: str,
        kind: str,
        content: bytes | str | dict[str, Any],
        filename: str | None = None,
    ) -> str:
        artifact_id = new_ulid()
        self._items[artifact_id] = (tenant_id, kind, content)
        del filename
        return artifact_id

    def get(self, artifact_id: str) -> bytes | str | dict[str, Any] | None:
        item = self._items.get(artifact_id)
        return item[2] if item is not None else None


__all__ = ["InMemoryEvidenceWriter", "sanitize_evidence"]
