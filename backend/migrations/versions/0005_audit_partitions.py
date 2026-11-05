"""partition audit_log by month

Revision ID: 0005_audit_partitions
Revises: 0004_audit_log
Create Date: 2026-11-05
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0005_audit_partitions"
down_revision: Union[str, None] = "0004_audit_log"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # MySQL requires every unique key to contain the partition column.
    op.execute("ALTER TABLE audit_log DROP PRIMARY KEY, ADD PRIMARY KEY (id, created_at)")
    op.execute(
        """
        ALTER TABLE audit_log
        PARTITION BY RANGE COLUMNS(created_at) (
            PARTITION p202610 VALUES LESS THAN ('2026-11-01'),
            PARTITION p202611 VALUES LESS THAN ('2026-12-01'),
            PARTITION p202612 VALUES LESS THAN ('2027-01-01'),
            PARTITION pmax VALUES LESS THAN (MAXVALUE)
        )
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE audit_log REMOVE PARTITIONING")
    op.execute("ALTER TABLE audit_log DROP PRIMARY KEY, ADD PRIMARY KEY (id)")
