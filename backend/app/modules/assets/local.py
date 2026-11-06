"""Local filesystem storage adapter for development and tests."""

from __future__ import annotations

import os
import time
from pathlib import Path

from app.core.errors import NotFoundError
from app.modules.assets.storage import (
    MAX_PRESIGN_TTL_SECONDS,
    sha256_hex,
    validate_key,
    validate_ttl,
)


class LocalStorage:
    """Private-root storage; keys are relative paths below ``root``."""

    def __init__(self, root: Path) -> None:
        self._root = Path(root).expanduser().resolve()
        self._root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        validate_key(key)
        path = (self._root / key).resolve()
        if self._root not in path.parents and path != self._root:
            raise ValueError("object key escapes the storage root")
        return path

    def put(self, key: str, data: bytes, *, content_type: str) -> str:
        del content_type
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return sha256_hex(data)

    def get(self, key: str) -> bytes:
        path = self._path(key)
        if not path.exists():
            raise NotFoundError("Object not found", key=key)
        return path.read_bytes()

    def delete(self, key: str) -> None:
        path = self._path(key)
        if path.exists():
            path.unlink()

    def presign_get(self, key: str, *, ttl_seconds: int = MAX_PRESIGN_TTL_SECONDS) -> str:
        validate_key(key)
        validate_ttl(ttl_seconds)
        expires = int(time.time()) + ttl_seconds
        return f"local://{key}?expires={expires}"

    def presign_put(self, key: str, *, ttl_seconds: int = MAX_PRESIGN_TTL_SECONDS) -> str:
        validate_key(key)
        validate_ttl(ttl_seconds)
        expires = int(time.time()) + ttl_seconds
        return f"local-put://{key}?expires={expires}"

    def healthcheck(self) -> bool:
        return self._root.exists() and os.access(self._root, os.W_OK)
