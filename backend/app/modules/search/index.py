"""Vector index implementations: in-memory and Qdrant-compatible."""

from __future__ import annotations

from typing import Any

from app.core.errors import InvalidArgumentError, UpstreamUnavailableError
from app.modules.search.embedding import cosine_similarity
from app.modules.search.public import SearchHit, VectorRecord

_ALLOWED_PAYLOAD_KEYS = {"tenant_id", "badcase_id", "dataset_id", "sample_id", "tags"}
_FORBIDDEN_PAYLOAD_KEYS = {
    "answer",
    "body",
    "content",
    "input",
    "message",
    "output",
    "prompt",
    "text",
}


def sanitize_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Keep only reference ids/tags; reject sample bodies outright."""

    forbidden = sorted(set(payload) & _FORBIDDEN_PAYLOAD_KEYS)
    if forbidden:
        raise InvalidArgumentError(
            "vector payload must contain reference ids only",
            forbidden=forbidden,
        )
    return {key: value for key, value in payload.items() if key in _ALLOWED_PAYLOAD_KEYS}


class InMemoryVectorIndex:
    """Deterministic cosine index used for tests and degraded local runs."""

    def __init__(self) -> None:
        self._records: dict[str, VectorRecord] = {}

    def upsert(self, records: list[VectorRecord]) -> int:
        written = 0
        for record in records:
            if not record.tenant_id:
                raise InvalidArgumentError("tenant_id is required for vector records")
            if not record.id:
                raise InvalidArgumentError("vector record id is required")
            payload = sanitize_payload(record.payload)
            payload["tenant_id"] = record.tenant_id
            payload.setdefault("badcase_id", record.id)
            self._records[record.id] = VectorRecord(
                id=record.id,
                tenant_id=record.tenant_id,
                vector=tuple(record.vector),
                payload=payload,
                metadata=dict(record.metadata),
            )
            written += 1
        return written

    def search(
        self,
        *,
        tenant_id: str,
        vector: list[float],
        dataset_id: str | None = None,
        tags: tuple[str, ...] = (),
        limit: int = 10,
    ) -> list[SearchHit]:
        wanted_tags = set(tags)
        hits: list[tuple[float, VectorRecord]] = []
        for record in self._records.values():
            if record.tenant_id != tenant_id:
                continue
            payload = record.payload
            if dataset_id is not None and payload.get("dataset_id") != dataset_id:
                continue
            record_tags = set(payload.get("tags") or ())
            if wanted_tags and not wanted_tags.issubset(record_tags):
                continue
            score = cosine_similarity(list(record.vector), vector)
            hits.append((score, record))
        hits.sort(key=lambda item: (-item[0], item[1].id))
        return [
            SearchHit(
                badcase_id=str(record.payload.get("badcase_id") or record.id),
                dataset_id=record.payload.get("dataset_id"),
                sample_id=record.payload.get("sample_id"),
                score=round(score, 6),
            )
            for score, record in hits[:limit]
        ]

    def delete(
        self,
        *,
        tenant_id: str,
        ids: list[str] | None = None,
        dataset_id: str | None = None,
    ) -> int:
        doomed = [
            record_id
            for record_id, record in self._records.items()
            if record.tenant_id == tenant_id
            and (ids is None or record_id in ids)
            and (dataset_id is None or record.payload.get("dataset_id") == dataset_id)
        ]
        for record_id in doomed:
            del self._records[record_id]
        return len(doomed)


class QdrantVectorIndex:
    """Qdrant-compatible adapter.

    ``qdrant_client`` is imported lazily so the module has no hard dependency
    on Qdrant and can be replaced by any :class:`VectorIndex` implementation.
    """

    def __init__(
        self,
        *,
        collection: str,
        client: Any | None = None,
        url: str | None = None,
        api_key: str | None = None,
        timeout_seconds: float = 1.0,
    ) -> None:
        if not collection:
            raise InvalidArgumentError("collection is required")
        self.collection = collection
        self._client = client
        self._url = url
        self._api_key = api_key
        self._timeout_seconds = timeout_seconds

    def _client_or_raise(self) -> Any:
        if self._client is not None:
            return self._client
        try:
            from qdrant_client import QdrantClient
        except ImportError as exc:
            raise UpstreamUnavailableError("qdrant-client is not installed") from exc
        self._client = QdrantClient(
            url=self._url,
            api_key=self._api_key,
            timeout=self._timeout_seconds,
        )
        return self._client

    def upsert(self, records: list[VectorRecord]) -> int:
        try:
            from qdrant_client.models import PointStruct
        except ImportError as exc:
            raise UpstreamUnavailableError("qdrant-client is not installed") from exc
        points = []
        for record in records:
            payload = sanitize_payload(record.payload)
            payload["tenant_id"] = record.tenant_id
            payload.setdefault("badcase_id", record.id)
            points.append(
                PointStruct(
                    id=record.id,
                    vector=list(record.vector),
                    payload=payload,
                )
            )
        self._client_or_raise().upsert(collection_name=self.collection, points=points, wait=True)
        return len(points)

    def search(
        self,
        *,
        tenant_id: str,
        vector: list[float],
        dataset_id: str | None = None,
        tags: tuple[str, ...] = (),
        limit: int = 10,
    ) -> list[SearchHit]:
        try:
            from qdrant_client.models import FieldCondition, Filter, MatchAny, MatchValue
        except ImportError as exc:
            raise UpstreamUnavailableError("qdrant-client is not installed") from exc
        must: list[Any] = [FieldCondition(key="tenant_id", match=MatchValue(value=tenant_id))]
        if dataset_id is not None:
            must.append(FieldCondition(key="dataset_id", match=MatchValue(value=dataset_id)))
        if tags:
            must.append(FieldCondition(key="tags", match=MatchAny(any=list(tags))))
        results = self._client_or_raise().search(
            collection_name=self.collection,
            query_vector=list(vector),
            query_filter=Filter(must=must),
            limit=limit,
            with_payload=True,
        )
        hits: list[SearchHit] = []
        for point in results:
            payload = getattr(point, "payload", None) or {}
            if payload.get("tenant_id") != tenant_id:
                continue
            hits.append(
                SearchHit(
                    badcase_id=str(payload.get("badcase_id") or getattr(point, "id", "")),
                    dataset_id=payload.get("dataset_id"),
                    sample_id=payload.get("sample_id"),
                    score=float(getattr(point, "score", 0.0)),
                )
            )
        return hits

    def delete(
        self,
        *,
        tenant_id: str,
        ids: list[str] | None = None,
        dataset_id: str | None = None,
    ) -> int:
        try:
            from qdrant_client.models import (
                FieldCondition,
                Filter,
                FilterSelector,
                MatchValue,
                PointIdsList,
            )
        except ImportError as exc:
            raise UpstreamUnavailableError("qdrant-client is not installed") from exc
        client = self._client_or_raise()
        if ids:
            client.delete(
                collection_name=self.collection,
                points_selector=PointIdsList(points=ids),
                wait=True,
            )
            return len(ids)
        must: list[Any] = [FieldCondition(key="tenant_id", match=MatchValue(value=tenant_id))]
        if dataset_id is not None:
            must.append(FieldCondition(key="dataset_id", match=MatchValue(value=dataset_id)))
        client.delete(
            collection_name=self.collection,
            points_selector=FilterSelector(filter=Filter(must=must)),
            wait=True,
        )
        return -1


__all__ = ["InMemoryVectorIndex", "QdrantVectorIndex", "sanitize_payload"]
