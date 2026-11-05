"""UTC clock helper tests (CORE-13)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

from app.core.clock import to_iso, utcnow, utcnow_naive


def test_utcnow_is_aware_utc() -> None:
    now = utcnow()
    assert now.tzinfo is UTC
    assert now.utcoffset() == timedelta(0)


def test_utcnow_naive_has_no_timezone() -> None:
    naive = utcnow_naive()
    assert naive.tzinfo is None


def test_to_iso_handles_none() -> None:
    assert to_iso(None) is None


def test_to_iso_assumes_naive_values_are_utc() -> None:
    assert to_iso(datetime(2026, 1, 1, 12, 0, 0)) == "2026-01-01T12:00:00+00:00"


def test_to_iso_converts_other_offsets_to_utc() -> None:
    value = datetime(2026, 1, 1, 20, 0, 0, tzinfo=timezone(timedelta(hours=8)))
    assert to_iso(value) == "2026-01-01T12:00:00+00:00"
