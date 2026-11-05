"""Embedding version metadata and double-write switching (SRC-03)."""

from __future__ import annotations

from app.core.errors import InvalidArgumentError
from app.modules.search.public import EmbeddingVersion


class EmbeddingVersionRegistry:
    """Tracks embedding versions and the active/double-write collection.

    Metadata only; vectors stay in Qdrant. Switching versions is a two-step
    operation: register the new version, then activate it after the rebuild.
    """

    def __init__(self) -> None:
        self._versions: dict[str, EmbeddingVersion] = {}
        self._active: str | None = None
        self._double_write: str | None = None

    def register(self, version: EmbeddingVersion) -> EmbeddingVersion:
        key = self._key(version.model, version.version)
        self._versions[key] = version
        if self._active is None:
            self._active = key
        return version

    def activate(self, model: str, version: str) -> EmbeddingVersion:
        key = self._key(model, version)
        if key not in self._versions:
            raise InvalidArgumentError("embedding version is not registered", model=model, version=version)
        self._double_write = self._active if self._active != key else None
        self._active = key
        return self._versions[key]

    def stop_double_write(self) -> None:
        self._double_write = None

    def active(self) -> EmbeddingVersion:
        if self._active is None:
            raise InvalidArgumentError("no embedding version is registered")
        return self._versions[self._active]

    def double_write_versions(self) -> tuple[EmbeddingVersion, ...]:
        if self._double_write is None:
            return ()
        return (self._versions[self._double_write],)

    def get(self, model: str, version: str) -> EmbeddingVersion:
        key = self._key(model, version)
        if key not in self._versions:
            raise InvalidArgumentError("embedding version is not registered", model=model, version=version)
        return self._versions[key]

    @staticmethod
    def _key(model: str, version: str) -> str:
        if not model or not version:
            raise InvalidArgumentError("embedding model and version are required")
        return f"{model}:{version}"


__all__ = ["EmbeddingVersionRegistry"]
