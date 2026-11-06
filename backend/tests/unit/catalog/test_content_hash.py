"""Catalog content-hash and normalization tests (CAT-03)."""

from __future__ import annotations

import pytest

from app.core.errors import InvalidArgumentError
from app.modules.catalog.service import content_hash


def test_content_hash_is_order_independent() -> None:
    first = [
        {"sample_key": "a", "payload": {"q": "1", "a": "2"}},
        {"sample_key": "b", "payload": {"q": "3", "a": "4"}},
    ]
    second = list(reversed(first))
    assert content_hash(first) == content_hash(second)
    assert len(content_hash(first)) == 64


def test_content_hash_changes_with_content() -> None:
    base = [{"sample_key": "a", "payload": {"q": "1"}}]
    changed = [{"sample_key": "a", "payload": {"q": "2"}}]
    assert content_hash(base) != content_hash(changed)


def test_content_hash_requires_sample_key() -> None:
    from app.modules.catalog.service import _normalize_samples

    with pytest.raises(InvalidArgumentError):
        _normalize_samples([{"payload": {"q": "1"}}])
