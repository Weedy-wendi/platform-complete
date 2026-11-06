"""Monthly partition maintenance for append-only audit tables.

Both `mcp_tool_call` and `audit_log` are partitioned by `created_at`. This
command pre-creates the next N monthly partitions and drops partitions whose
data is older than the retention window. It needs DDL privileges (run with an
admin/root DSN), never with the runtime accounts.
"""

from __future__ import annotations

import argparse
import calendar
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

import pymysql
from sqlalchemy.engine import make_url

DEFAULT_TABLE = "mcp_tool_call"


@dataclass(frozen=True)
class PartitionPlan:
    create: list[tuple[int, int]]
    drop: list[str]

    @property
    def create_names(self) -> list[str]:
        return [partition_name(year, month) for year, month in self.create]


def partition_name(year: int, month: int) -> str:
    return f"p{year:04d}{month:02d}"


def _next_month(year: int, month: int) -> tuple[int, int]:
    if month == 12:
        return year + 1, 1
    return year, month + 1


def upcoming_months(today: date, months_ahead: int) -> list[tuple[int, int]]:
    if months_ahead < 0:
        raise ValueError("months_ahead must be >= 0")
    result: list[tuple[int, int]] = []
    year, month = today.year, today.month
    for _ in range(months_ahead):
        year, month = _next_month(year, month)
        result.append((year, month))
    return result


def _month_end(year: int, month: int) -> date:
    return date(year, month, calendar.monthrange(year, month)[1])


def is_expired(partition: str, today: date, retention_days: int) -> bool:
    if not partition.startswith("p") or len(partition) != 7 or not partition[1:].isdigit():
        return False
    year = int(partition[1:5])
    month = int(partition[5:7])
    if not 1 <= month <= 12:
        return False
    cutoff = today - timedelta(days=retention_days)
    return _month_end(year, month) < cutoff


def plan_partitions(
    existing: Iterable[str],
    today: date,
    *,
    months_ahead: int = 3,
    retention_days: int = 90,
) -> PartitionPlan:
    names = set(existing)
    create = [
        (year, month)
        for year, month in upcoming_months(today, months_ahead)
        if partition_name(year, month) not in names
    ]
    drop = [name for name in sorted(names) if name != "pmax" and is_expired(name, today, retention_days)]
    return PartitionPlan(create=create, drop=drop)


def build_reorganize_sql(table: str, months: list[tuple[int, int]]) -> str:
    clauses = []
    for year, month in months:
        next_year, next_month = _next_month(year, month)
        clauses.append(
            f"PARTITION {partition_name(year, month)} VALUES LESS THAN ('{next_year:04d}-{next_month:02d}-01')"
        )
    clauses.append("PARTITION pmax VALUES LESS THAN (MAXVALUE)")
    return f"ALTER TABLE `{table}` REORGANIZE PARTITION pmax INTO ({', '.join(clauses)})"


def build_drop_sql(table: str, partitions: list[str]) -> str:
    return f"ALTER TABLE `{table}` DROP PARTITION {', '.join(partitions)}"


def _existing_partitions(connection: pymysql.connections.Connection, database: str, table: str) -> list[str]:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT PARTITION_NAME
            FROM information_schema.PARTITIONS
            WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s AND PARTITION_NAME IS NOT NULL
            """,
            (database, table),
        )
        return [row[0] for row in cursor.fetchall()]


def run(
    *,
    dsn: str,
    months_ahead: int = 3,
    retention_days: int = 90,
    dry_run: bool = False,
    table: str = DEFAULT_TABLE,
) -> int:
    if not dsn:
        print("A DSN with DDL privileges is required (--dsn or PINGCE_MCP_DB_DSN)")
        return 2
    url = make_url(dsn)
    connection = pymysql.connect(
        host=url.host or "127.0.0.1",
        port=url.port or 3306,
        user=url.username or "root",
        password=url.password or "",
        database=url.database or "pingce",
        charset="utf8mb4",
        autocommit=True,
        connect_timeout=5,
    )
    try:
        existing = _existing_partitions(connection, url.database or "pingce", table)
        plan = plan_partitions(
            existing,
            datetime.now(UTC).date(),
            months_ahead=months_ahead,
            retention_days=retention_days,
        )
        print(f"existing: {sorted(existing)}")
        print(f"create:   {plan.create_names}")
        print(f"drop:     {plan.drop}")
        if dry_run:
            return 0
        with connection.cursor() as cursor:
            if plan.create:
                cursor.execute(build_reorganize_sql(table, plan.create))
            if plan.drop:
                cursor.execute(build_drop_sql(table, plan.drop))
        print("partition maintenance complete")
        return 0
    finally:
        connection.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Maintain monthly audit partitions")
    parser.add_argument("--dsn", required=True)
    parser.add_argument("--table", default=DEFAULT_TABLE)
    parser.add_argument("--months-ahead", type=int, default=3)
    parser.add_argument("--retention-days", type=int, default=90)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    return run(
        dsn=args.dsn,
        months_ahead=args.months_ahead,
        retention_days=args.retention_days,
        dry_run=args.dry_run,
        table=args.table,
    )


if __name__ == "__main__":
    raise SystemExit(main())
