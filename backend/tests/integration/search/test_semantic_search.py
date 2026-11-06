"""Semantic search: relevance, degraded fallback and filters (SRC-05/06)."""

from __future__ import annotations

from app.core.context import TenantContext
from app.modules.search.embedding import HashingEmbedder
from app.modules.search.index import InMemoryVectorIndex
from app.modules.search.keyword import InMemoryKeywordIndex, KeywordRecord
from app.modules.search.public import EmbeddingVersion, SearchHit
from app.modules.search.service import SemanticSearchService


class FailingIndex:
    def upsert(self, records):
        return 0

    def search(self, **kwargs):
        raise TimeoutError("qdrant timed out")

    def delete(self, **kwargs):
        return 0


def _service(index=None, keyword=None) -> SemanticSearchService:
    keyword = keyword or InMemoryKeywordIndex()
    return SemanticSearchService(
        index=index or InMemoryVectorIndex(),
        embedder=HashingEmbedder(32),
        keyword=keyword,
        embedding_version=EmbeddingVersion("hash", "v1", 32, "badcases_v1"),
    )


def _ctx(tenant_id: str = "tenant-a") -> TenantContext:
    return TenantContext(tenant_id=tenant_id, subject_id="user:1")


def test_semantic_search_returns_relevant_hits_and_scores() -> None:
    service = _service()
    service.index_badcase(
        _ctx(),
        badcase_id="b1",
        text="login failure when password expires",
        dataset_id="d1",
        sample_id="s1",
        tags=("auth",),
    )
    service.index_badcase(
        _ctx(),
        badcase_id="b2",
        text="payment success receipt",
        dataset_id="d1",
        sample_id="s2",
        tags=("billing",),
    )

    result = service.search_badcases(tenant_id="tenant-a", query="login password", dataset_id=None, tags=(), limit=10)

    assert result.degraded is False
    assert result.hits[0].badcase_id == "b1"
    assert result.hits[0].score is not None
    assert result.hits[0].dataset_id == "d1"
    assert result.hits[0].sample_id == "s1"


def test_degraded_search_uses_keyword_index() -> None:
    keyword = InMemoryKeywordIndex()
    keyword.upsert(
        [
            KeywordRecord(
                tenant_id="tenant-a",
                badcase_id="b1",
                text="login failure",
                dataset_id="d1",
                sample_id="s1",
                tags=("auth",),
            )
        ]
    )
    service = _service(index=FailingIndex(), keyword=keyword)

    result = service.search_badcases(tenant_id="tenant-a", query="login", dataset_id=None, tags=(), limit=10)

    assert result.degraded is True
    assert [hit.badcase_id for hit in result.hits] == ["b1"]
    assert result.hits[0].score is not None


def test_dataset_and_tag_filters() -> None:
    service = _service()
    service.index_badcase(_ctx(), badcase_id="b1", text="login failure", dataset_id="d1", tags=("auth",))
    service.index_badcase(_ctx(), badcase_id="b2", text="login failure", dataset_id="d2", tags=("auth", "beta"))

    by_dataset = service.search_badcases(tenant_id="tenant-a", query="login", dataset_id="d2", tags=(), limit=10)
    assert [hit.badcase_id for hit in by_dataset.hits] == ["b2"]

    by_tag = service.search_badcases(tenant_id="tenant-a", query="login", dataset_id=None, tags=("beta",), limit=10)
    assert [hit.badcase_id for hit in by_tag.hits] == ["b2"]


def test_top_k_is_capped_at_fifty() -> None:
    service = _service()
    for index in range(60):
        service.index_badcase(_ctx(), badcase_id=f"b{index}", text="same text", dataset_id="d1")
    result = service.search_badcases(tenant_id="tenant-a", query="same", dataset_id=None, tags=(), limit=500)
    assert len(result.hits) == 50


def test_no_query_uses_keyword_filter_without_degraded_flag() -> None:
    keyword = InMemoryKeywordIndex()
    keyword.upsert([KeywordRecord(tenant_id="tenant-a", badcase_id="b1", text="anything")])
    service = _service(keyword=keyword)
    result = service.search_badcases(tenant_id="tenant-a", query=None, dataset_id=None, tags=(), limit=10)
    assert result.degraded is False
    assert [hit.badcase_id for hit in result.hits] == ["b1"]


def test_cross_tenant_semantic_search_is_empty() -> None:
    service = _service()
    service.index_badcase(_ctx("tenant-a"), badcase_id="b1", text="login failure", dataset_id="d1")
    service.index_badcase(_ctx("tenant-b"), badcase_id="b2", text="login failure", dataset_id="d1")

    result = service.search_badcases(tenant_id="tenant-a", query="login", dataset_id=None, tags=(), limit=50)
    assert [hit.badcase_id for hit in result.hits] == ["b1"]
    assert all(hit.badcase_id != "b2" for hit in result.hits)


def test_indexed_payload_contains_only_reference_ids() -> None:
    index = InMemoryVectorIndex()
    service = _service(index=index)
    record_id = service.index_badcase(
        _ctx(),
        badcase_id="b1",
        text="very secret prompt text",
        dataset_id="d1",
        sample_id="s1",
        tags=("auth",),
    )
    record = index._records[record_id]  # noqa: SLF001 - security assertion on stored payload
    assert "very secret prompt text" not in str(record.payload)
    assert set(record.payload) <= {"tenant_id", "badcase_id", "dataset_id", "sample_id", "tags"}
    assert record.metadata["embedding_model"] == "hash"


def test_search_hit_shape_matches_contract() -> None:
    hit = SearchHit(badcase_id="b1", dataset_id=None, sample_id=None, score=None)
    assert hit.badcase_id == "b1"
