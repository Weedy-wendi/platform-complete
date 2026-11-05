"""Search primitives: hashing embedder, payload policy, limit clamp."""

from __future__ import annotations

import pytest

from app.core.errors import InvalidArgumentError
from app.modules.search.embedding import HashingEmbedder, cosine_similarity
from app.modules.search.index import sanitize_payload
from app.modules.search.service import clamp_search_limit


def test_hashing_embedder_is_deterministic_and_normalized() -> None:
    embedder = HashingEmbedder(16)
    first = embedder.embed("login failure timeout")
    second = embedder.embed("login failure timeout")
    assert first == second
    assert len(first) == 16
    assert cosine_similarity(first, first) == pytest.approx(1.0)
    assert first != embedder.embed("payment success")


def test_hashing_embedder_leaves_zero_vector_for_empty_text() -> None:
    assert HashingEmbedder(8).embed("") == [0.0] * 8


def test_payload_policy_rejects_bodies() -> None:
    with pytest.raises(InvalidArgumentError):
        sanitize_payload({"badcase_id": "b1", "prompt": "secret prompt"})
    with pytest.raises(InvalidArgumentError):
        sanitize_payload({"badcase_id": "b1", "answer": "secret answer"})
    assert sanitize_payload({"badcase_id": "b1", "dataset_id": "d1", "tags": ["x"]}) == {
        "badcase_id": "b1",
        "dataset_id": "d1",
        "tags": ["x"],
    }


def test_limit_defaults_and_caps() -> None:
    assert clamp_search_limit(None) == 10
    assert clamp_search_limit(0) == 10
    assert clamp_search_limit(5) == 5
    assert clamp_search_limit(500) == 50
