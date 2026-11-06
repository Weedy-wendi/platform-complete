"""In-memory keyword fallback used when the vector index is unavailable."""

from __future__ import annotations

from dataclasses import dataclass, field

from app.core.errors import InvalidArgumentError
from app.modules.search.embedding import tokenize
from app.modules.search.public import SearchHit


@dataclass(frozen=True)
class KeywordRecord:
    tenant_id: str
    badcase_id: str
    text: str = ""
    dataset_id: str | None = None
    sample_id: str | None = None
    tags: tuple[str, ...] = field(default_factory=tuple)


class InMemoryKeywordIndex:
    """Tenant-scoped keyword index with a deterministic scoring function."""

    def __init__(self) -> None:
        self._records: dict[tuple[str, str], KeywordRecord] = {}

    def upsert(self, records: list[KeywordRecord]) -> int:
        for record in records:
            if not record.tenant_id or not record.badcase_id:
                raise InvalidArgumentError("tenant_id and badcase_id are required")
            self._records[(record.tenant_id, record.badcase_id)] = record
        return len(records)

    def delete(self, *, tenant_id: str, badcase_ids: list[str] | None = None) -> int:
        doomed = [
            key for key in self._records if key[0] == tenant_id and (badcase_ids is None or key[1] in badcase_ids)
        ]
        for key in doomed:
            del self._records[key]
        return len(doomed)

    def search(
        self,
        *,
        tenant_id: str,
        query: str | None,
        dataset_id: str | None = None,
        tags: tuple[str, ...] = (),
        limit: int = 10,
    ) -> list[SearchHit]:
        wanted_tags = set(tags)
        query_tokens = set(tokenize(query or ""))
        scored: list[tuple[float, KeywordRecord]] = []
        for record in self._records.values():
            if record.tenant_id != tenant_id:
                continue
            if dataset_id is not None and record.dataset_id != dataset_id:
                continue
            if wanted_tags and not wanted_tags.issubset(set(record.tags)):
                continue
            if query_tokens:
                record_tokens = set(tokenize(record.text))
                overlap = len(query_tokens & record_tokens)
                substring = 1.0 if (query or "").lower() in record.text.lower() else 0.0
                score = overlap / len(query_tokens) + substring
                if score <= 0:
                    continue
            else:
                score = 0.0
            scored.append((score, record))
        scored.sort(key=lambda item: (-item[0], item[1].badcase_id))
        return [
            SearchHit(
                badcase_id=record.badcase_id,
                dataset_id=record.dataset_id,
                sample_id=record.sample_id,
                score=round(score, 6),
            )
            for score, record in scored[:limit]
        ]


__all__ = ["InMemoryKeywordIndex", "KeywordRecord"]
