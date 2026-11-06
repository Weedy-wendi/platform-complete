"""Partition retention planning tests (AUD-02)."""

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


def test_partition_name_and_upcoming_months() -> None:
    assert partition_name(2026, 11) == "p202611"
    assert upcoming_months(date(2026, 11, 5), 3) == [(2026, 12), (2027, 1), (2027, 2)]


def test_is_expired_uses_retention_days() -> None:
    today = date(2026, 11, 5)
    assert is_expired("p202604", today, retention_days=180) is True
    assert is_expired("p202605", today, retention_days=180) is False
    assert is_expired("pmax", today, retention_days=180) is False
    assert is_expired("not-a-partition", today, retention_days=180) is False


def test_plan_drops_expired_and_creates_upcoming() -> None:
    plan = plan_partitions(
        ["p202604", "p202605", "p202611", "pmax"],
        date(2026, 11, 5),
        months_ahead=2,
        retention_days=180,
    )
    assert plan.drop == ["p202604"]
    assert plan.create_names == ["p202612", "p202701"]


def test_sql_targets_audit_table() -> None:
    reorganize = build_reorganize_sql("audit_log", [(2026, 12)])
    assert "`audit_log`" in reorganize
    assert "p202612" in reorganize
    assert "pmax" in reorganize
    assert build_drop_sql("audit_log", ["p202604"]) == "ALTER TABLE `audit_log` DROP PARTITION p202604"
