import pytest

from app.core.errors import InvalidCursorError
from app.mcp.cursor import CursorCodec, query_fingerprint


def test_round_trip() -> None:
    codec = CursorCodec("secret", ttl_seconds=60)
    cursor = codec.encode(tenant_id="tenant-a", tool="search_datasets", query_hash="q1", last_key={"id": "1"})
    payload = codec.decode(cursor, tenant_id="tenant-a", tool="search_datasets", query_hash="q1")
    assert payload["k"] == {"id": "1"}


def test_tampered_cursor_is_rejected() -> None:
    codec = CursorCodec("secret", ttl_seconds=60)
    cursor = codec.encode(tenant_id="tenant-a", tool="search_datasets", query_hash="q1", last_key="1")
    with pytest.raises(InvalidCursorError):
        codec.decode(cursor[:-1] + "x", tenant_id="tenant-a", tool="search_datasets", query_hash="q1")


def test_cross_tenant_cursor_is_rejected() -> None:
    codec = CursorCodec("secret", ttl_seconds=60)
    cursor = codec.encode(tenant_id="tenant-a", tool="search_datasets", query_hash="q1", last_key="1")
    with pytest.raises(InvalidCursorError):
        codec.decode(cursor, tenant_id="tenant-b", tool="search_datasets", query_hash="q1")


def test_expired_cursor_is_rejected() -> None:
    codec = CursorCodec("secret", ttl_seconds=-1)
    cursor = codec.encode(tenant_id="tenant-a", tool="search_datasets", query_hash="q1", last_key="1")
    with pytest.raises(InvalidCursorError):
        codec.decode(cursor, tenant_id="tenant-a", tool="search_datasets", query_hash="q1")


def test_query_fingerprint_is_stable() -> None:
    assert query_fingerprint({"a": 1, "b": 2}) == query_fingerprint({"b": 2, "a": 1})
    assert query_fingerprint({"a": 1}) != query_fingerprint({"a": 2})


def test_invalid_cursor_increments_metric() -> None:
    from app.core.metrics import MCP_CURSOR_INVALID

    before = MCP_CURSOR_INVALID._value.get()  # type: ignore[attr-defined]
    codec = CursorCodec("secret", ttl_seconds=60)
    with pytest.raises(InvalidCursorError):
        codec.decode("not-a-cursor", tenant_id="tenant-a", tool="search_datasets", query_hash="q1")
    assert MCP_CURSOR_INVALID._value.get() == before + 1  # type: ignore[attr-defined]
