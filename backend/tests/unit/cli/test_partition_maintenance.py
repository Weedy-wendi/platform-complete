"""Partition maintenance helpers (T082)."""

from __future__ import annotations

from datetime import date

from app.cli.maintain_partitions import (
    build_drop_sql,
    build_reorganize_sql,
    is_expired,
    partition_name,
    plan_partitions,
    upcoming_months,
)


def test_partition_name() -> None:
    assert partition_name(2026, 11) == "p202611"
    assert partition_name(2027, 1) == "p202701"


def test_upcoming_months_crosses_year_boundary() -> None:
    assert upcoming_months(date(2026, 11, 15), 3) == [(2026, 12), (2027, 1), (2027, 2)]


def test_is_expired_uses_month_end_and_retention() -> None:
    today = date(2026, 11, 15)
    assert is_expired("p202606", today, 90) is True
    assert is_expired("p202609", today, 90) is False
    assert is_expired("pmax", today, 90) is False
    assert is_expired("not-a-partition", today, 90) is False


def test_plan_partitions_creates_missing_and_drops_expired() -> None:
    plan = plan_partitions(
        ["p202606", "p202611", "pmax"],
        date(2026, 11, 15),
        months_ahead=2,
        retention_days=90,
    )
    assert plan.create == [(2026, 12), (2027, 1)]
    assert plan.create_names == ["p202612", "p202701"]
    assert plan.drop == ["p202606"]


def test_sql_builders() -> None:
    reorganize = build_reorganize_sql("mcp_tool_call", [(2026, 12), (2027, 1)])
    assert "REORGANIZE PARTITION pmax" in reorganize
    assert "PARTITION p202612 VALUES LESS THAN ('2027-01-01')" in reorganize
    assert "PARTITION p202701 VALUES LESS THAN ('2027-02-01')" in reorganize
    assert "PARTITION pmax VALUES LESS THAN (MAXVALUE)" in reorganize

    drop = build_drop_sql("mcp_tool_call", ["p202606", "p202607"])
    assert drop == "ALTER TABLE `mcp_tool_call` DROP PARTITION p202606, p202607"
