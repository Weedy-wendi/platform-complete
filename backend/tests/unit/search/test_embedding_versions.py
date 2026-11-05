"""Embedding version metadata and double-write switching (SRC-03)."""

from __future__ import annotations

import pytest

from app.core.errors import InvalidArgumentError
from app.modules.search.public import EmbeddingVersion
from app.modules.search.versions import EmbeddingVersionRegistry


def test_register_activate_and_double_write() -> None:
    registry = EmbeddingVersionRegistry()
    v1 = registry.register(EmbeddingVersion("hash", "v1", 32, "badcases_v1"))
    assert registry.active() == v1

    v2 = registry.register(EmbeddingVersion("hash", "v2", 64, "badcases_v2"))
    assert registry.active() == v1
    assert registry.activate("hash", "v2") == v2
    assert registry.active() == v2
    assert registry.double_write_versions() == (v1,)

    registry.stop_double_write()
    assert registry.double_write_versions() == ()


def test_unknown_embedding_version_is_rejected() -> None:
    registry = EmbeddingVersionRegistry()
    with pytest.raises(InvalidArgumentError):
        registry.active()
    with pytest.raises(InvalidArgumentError):
        registry.activate("missing", "v1")


def test_embedding_version_rejects_bad_dimension() -> None:
    with pytest.raises(ValueError):
        EmbeddingVersion("hash", "v1", 0, "badcases")
