"""Badcase read service (delegates retrieval to the semantic search module)."""

from __future__ import annotations

from app.services.models import BadcaseSearchResult
from app.services.search import SemanticSearch


class BadcaseService:
    def __init__(self, search: SemanticSearch) -> None:
        self._search = search

    def search_badcases(
        self,
        tenant_id: str,
        *,
        query: str | None = None,
        dataset_id: str | None = None,
        tags: tuple[str, ...] = (),
        limit: int = 20,
    ) -> BadcaseSearchResult:
        result = self._search.search_badcases(
            tenant_id=tenant_id,
            query=query,
            dataset_id=dataset_id,
            tags=tags,
            limit=limit,
        )
        # Defense in depth: never surface a hit from another tenant even if the
        # upstream service misbehaves.
        hits = [hit for hit in result.hits if hit.badcase.tenant_id == tenant_id]
        return BadcaseSearchResult(hits=hits, degraded=result.degraded)
