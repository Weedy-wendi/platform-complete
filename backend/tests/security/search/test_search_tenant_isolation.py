"""Search tenant isolation and payload leakage checks (SRC-06)."""

from __future__ import annotations

import pytest

from app.core.context import TenantContext
from app.core.errors import InvalidArgumentError
from app.modules.search.embedding import HashingEmbedder
from app.modules.search.index import InMemoryVectorIndex, sanitize_payload
from app.modules.search.keyword import InMemoryKeywordIndex, KeywordRecord
from app.modules.search.service import SemanticSearchService


def _service() -> SemanticSearchService:
    return SemanticSearchService(
        index=InMemoryVectorIndex(),
        embedder=HashingEmbedder(16),
        keyword=InMemoryKeywordIndex(),
    )


def test_search_never_returns_other_tenants() -> None:
    service = _service()
    service.index_badcase(
        ctx=TenantContext(tenant_id="tenant-a", subject_id="a"),
        badcase_id="a-1",
        text="shared keyword",
    )
    service.index_badcase(
        ctx=TenantContext(tenant_id="tenant-b", subject_id="b"),
        badcase_id="b-1",
        text="shared keyword",
    )

    tenant_b = service.search_badcases(tenant_id="tenant-b", query="shared keyword", dataset_id=None, tags=(), limit=50)
    assert [hit.badcase_id for hit in tenant_b.hits] == ["b-1"]


def test_tenant_id_is_required() -> None:
    service = _service()
    with pytest.raises(InvalidArgumentError):
        service.search_badcases(tenant_id="", query="x", dataset_id=None, tags=(), limit=10)


def test_keyword_fallback_is_tenant_scoped() -> None:
    keyword = InMemoryKeywordIndex()
    keyword.upsert(
        [
            KeywordRecord(tenant_id="tenant-a", badcase_id="a-1", text="login"),
            KeywordRecord(tenant_id="tenant-b", badcase_id="b-1", text="login"),
        ]
    )
    hits = keyword.search(tenant_id="tenant-a", query="login", limit=50)
    assert [hit.badcase_id for hit in hits] == ["a-1"]


def test_payload_rejects_body_content() -> None:
    with pytest.raises(InvalidArgumentError):
        sanitize_payload({"badcase_id": "b1", "text": "sample body"})
    with pytest.raises(InvalidArgumentError):
        sanitize_payload({"badcase_id": "b1", "content": "sample body"})
