"""Semantic search boundary.

`search_badcases` must delegate to the platform's semantic search service
(SRC-05). The MCP layer must not implement retrieval or fallback logic; it only
maps the service result to a tool response. When the service is not wired, the
tool returns ``UPSTREAM_UNAVAILABLE`` while staying registered.
"""

from __future__ import annotations

from typing import Protocol

from app.core.errors import UpstreamUnavailableError
from app.services.models import BadcaseSearchResult


class SemanticSearch(Protocol):
    def search_badcases(
        self,
        *,
        tenant_id: str,
        query: str | None,
        dataset_id: str | None,
        tags: tuple[str, ...],
        limit: int,
    ) -> BadcaseSearchResult: ...


class UnavailableSemanticSearch:
    """Dependency placeholder used until SRC-05 is deployed."""

    def search_badcases(
        self,
        *,
        tenant_id: str,
        query: str | None,
        dataset_id: str | None,
        tags: tuple[str, ...],
        limit: int,
    ) -> BadcaseSearchResult:
        raise UpstreamUnavailableError("Semantic search is not available")
