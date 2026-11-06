"""Storage SPI and key rules shared by all object-store adapters."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Protocol

from app.core.errors import InvalidArgumentError

MAX_PRESIGN_TTL_SECONDS = 900


class Storage(Protocol):
    def put(self, key: str, data: bytes, *, content_type: str) -> str: ...
    def get(self, key: str) -> bytes: ...
    def delete(self, key: str) -> None: ...
    def presign_get(self, key: str, *, ttl_seconds: int = MAX_PRESIGN_TTL_SECONDS) -> str: ...
    def presign_put(self, key: str, *, ttl_seconds: int = MAX_PRESIGN_TTL_SECONDS) -> str: ...
    def healthcheck(self) -> bool: ...


def validate_ttl(ttl_seconds: int) -> int:
    if not 0 < ttl_seconds <= MAX_PRESIGN_TTL_SECONDS:
        raise InvalidArgumentError(
            f"presign ttl_seconds must be between 1 and {MAX_PRESIGN_TTL_SECONDS}",
            ttl_seconds=ttl_seconds,
        )
    return ttl_seconds


def validate_key(key: str) -> str:
    if not key or key.startswith("/") or ".." in key.split("/") or key.endswith("/"):
        raise InvalidArgumentError("invalid object key", key=key)
    if len(key) > 512:
        raise InvalidArgumentError("object key is too long", key=key)
    return key


def build_key(
    *,
    tenant_id: str,
    asset_type: str,
    asset_id: str,
    version: str,
    filename: str,
) -> str:
    safe_filename = Path(filename).name
    if safe_filename != filename or ".." in safe_filename:
        raise InvalidArgumentError("invalid artifact filename", filename=filename)
    parts = [tenant_id, asset_type, asset_id, version, safe_filename]
    if any(not part or part in {".", ".."} or "/" in part for part in parts):
        raise InvalidArgumentError("invalid artifact key component")
    return validate_key(f"tenant/{'/'.join(parts)}")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
