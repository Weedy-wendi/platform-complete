"""Semantic search orchestration with automatic keyword degradation (SRC-05)."""

from __future__ import annotations

from app.core.context import TenantContext
from app.core.errors import InvalidArgumentError
from app.core.ids import new_ulid
from app.modules.search.public import (
    BadcaseSearchResult,
    Embedder,
    EmbeddingVersion,
    KeywordIndex,
    VectorIndex,
    VectorRecord,
)

DEFAULT_LIMIT = 10
MAX_LIMIT = 50


def clamp_search_limit(limit: int | None) -> int:
    if limit is None:
        return DEFAULT_LIMIT
    if limit < 1:
        return DEFAULT_LIMIT
    return min(limit, MAX_LIMIT)


class SemanticSearchService:
    """Qdrant-backed search with a fail-open MySQL keyword fallback.

    Any index/embedding failure is converted into a degraded keyword search;
    callers never see a 5xx because Qdrant is down.
    """

    def __init__(
        self,
        *,
        index: VectorIndex,
        embedder: Embedder,
        keyword: KeywordIndex,
        embedding_version: EmbeddingVersion | None = None,
    ) -> None:
        self._index = index
        self._embedder = embedder
        self._keyword = keyword
        self._embedding_version = embedding_version

    @property
    def embedding_version(self) -> EmbeddingVersion | None:
        return self._embedding_version

    def index_badcase(
        self,
        ctx: TenantContext,
        *,
        badcase_id: str,
        text: str,
        dataset_id: str | None = None,
        sample_id: str | None = None,
        tags: tuple[str, ...] = (),
    ) -> str:
        if not badcase_id.strip():
            raise InvalidArgumentError("badcase_id is required")
        record_id = new_ulid()
        payload = {
            "badcase_id": badcase_id,
            "dataset_id": dataset_id,
            "sample_id": sample_id,
            "tags": list(tags),
        }
        metadata: dict[str, object] = {}
        if self._embedding_version is not None:
            metadata = {
                "embedding_model": self._embedding_version.model,
                "embedding_version": self._embedding_version.version,
                "embedding_dim": self._embedding_version.dimension,
            }
        self._index.upsert(
            [
                VectorRecord(
                    id=record_id,
                    tenant_id=ctx.tenant_id,
                    vector=tuple(self._embedder.embed(text)),
                    payload=payload,
                    metadata=metadata,
                )
            ]
        )
        return record_id

    def search_badcases(
        self,
        *,
        tenant_id: str,
        query: str | None,
        dataset_id: str | None,
        tags: tuple[str, ...],
        limit: int,
    ) -> BadcaseSearchResult:
        if not tenant_id or not tenant_id.strip():
            raise InvalidArgumentError("tenant_id is required")
        resolved_limit = clamp_search_limit(limit)
        if query is None or not query.strip():
            return BadcaseSearchResult(
                hits=self._keyword.search(
                    tenant_id=tenant_id,
                    query=None,
                    dataset_id=dataset_id,
                    tags=tags,
                    limit=resolved_limit,
                ),
                degraded=False,
            )
        try:
            vector = self._embedder.embed(query)
            hits = self._index.search(
                tenant_id=tenant_id,
                vector=vector,
                dataset_id=dataset_id,
                tags=tags,
                limit=resolved_limit,
            )
            return BadcaseSearchResult(hits=hits, degraded=False)
        except Exception:  # noqa: BLE001 - degradation is the contract
            return self._degraded(
                tenant_id=tenant_id,
                query=query,
                dataset_id=dataset_id,
                tags=tags,
                limit=resolved_limit,
            )

    def _degraded(
        self,
        *,
        tenant_id: str,
        query: str,
        dataset_id: str | None,
        tags: tuple[str, ...],
        limit: int,
    ) -> BadcaseSearchResult:
        try:
            hits = self._keyword.search(
                tenant_id=tenant_id,
                query=query,
                dataset_id=dataset_id,
                tags=tags,
                limit=limit,
            )
        except Exception:  # noqa: BLE001 - keep the read path non-failing
            hits = []
        return BadcaseSearchResult(hits=hits, degraded=True)


__all__ = ["DEFAULT_LIMIT", "MAX_LIMIT", "SemanticSearchService", "clamp_search_limit"]
