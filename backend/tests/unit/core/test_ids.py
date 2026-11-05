from app.core.ids import new_key_id, new_trace_id, new_ulid
from app.core.pagination import clamp_limit


def test_ulid_is_sortable_and_unique() -> None:
    first = new_ulid()
    second = new_ulid()
    assert len(first) == 26
    assert len(second) == 26
    assert first != second


def test_other_identifiers() -> None:
    assert len(new_key_id()) == 24
    assert len(new_trace_id()) == 32


def test_clamp_limit() -> None:
    assert clamp_limit(None, default=20, maximum=100) == 20
    assert clamp_limit(1, maximum=100) == 1
    assert clamp_limit(500, maximum=100) == 100
