"""Public search contract.

Vectors live in Qdrant (or an injected index); MySQL only stores reference
metadata. Payloads must never contain the sample body or PII.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from app.core.context import TenantContext


@dataclass(frozen=True)
class SearchHit:
    badcase_id: str
    dataset_id: str | None = None
    sample_id: str | None = None
    score: float | None = None


@dataclass(frozen=True)
class BadcaseSearchResult:
    hits: list[SearchHit] = field(default_factory=list)
    degraded: bool = False


@dataclass(frozen=True)
class VectorRecord:
    """One indexed badcase.

    ``payload`` is restricted to reference ids and tags. ``metadata`` carries
    the embedding version and is not exposed to search callers.
    """

    id: str
    tenant_id: str
    vector: tuple[float, ...]
    payload: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EmbeddingVersion:
    model: str
    version: str
    dimension: int
    collection: str

    def __post_init__(self) -> None:
        if self.dimension <= 0:
            raise ValueError("embedding dimension must be positive")
        if not self.collection:
            raise ValueError("collection is required")


class VectorIndex(Protocol):
    """Replaceable vector index (Qdrant compatible)."""

    def upsert(self, records: list[VectorRecord]) -> int: ...

    def search(
        self,
        *,
        tenant_id: str,
        vector: list[float],
        dataset_id: str | None = None,
        tags: tuple[str, ...] = (),
        limit: int = 10,
    ) -> list[SearchHit]: ...

    def delete(
        self,
        *,
        tenant_id: str,
        ids: list[str] | None = None,
        dataset_id: str | None = None,
    ) -> int: ...


class Embedder(Protocol):
    def embed(self, text: str) -> list[float]: ...


class KeywordIndex(Protocol):
    """MySQL keyword fallback surface."""

    def search(
        self,
        *,
        tenant_id: str,
        query: str | None,
        dataset_id: str | None = None,
        tags: tuple[str, ...] = (),
        limit: int = 10,
    ) -> list[SearchHit]: ...


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


class BadcaseSearchService(SemanticSearch, Protocol):
    def index_badcase(
        self,
        ctx: TenantContext,
        *,
        badcase_id: str,
        text: str,
        dataset_id: str | None = None,
        sample_id: str | None = None,
        tags: tuple[str, ...] = (),
    ) -> str: ...


__all__ = [
    "BadcaseSearchResult",
    "BadcaseSearchService",
    "EmbeddingVersion",
    "Embedder",
    "KeywordIndex",
    "SearchHit",
    "SemanticSearch",
    "VectorIndex",
    "VectorRecord",
]
