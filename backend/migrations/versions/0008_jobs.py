"""create jobs tables

Revision ID: 0008_jobs
Revises: 0007_catalog
Create Date: 2026-11-05
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "0008_jobs"
down_revision: Union[str, None] = "0007_catalog"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "job",
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("tenant_id", sa.String(length=32), nullable=False),
        sa.Column("job_type", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("progress", sa.Integer(), nullable=False),
        sa.Column("last_error", sa.String(length=1024), nullable=True),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("updated_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("started_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("finished_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("created_by", sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "idempotency_key", name="uk_job_tenant_idempotency"),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_ai_ci",
    )
    op.create_index("idx_job_tenant_status", "job", ["tenant_id", "status", "updated_at"])

    op.create_table(
        "job_event",
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("tenant_id", sa.String(length=32), nullable=False),
        sa.Column("job_id", sa.String(length=26), nullable=False),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_ai_ci",
    )
    op.create_index("idx_job_event_tenant_job", "job_event", ["tenant_id", "job_id", "created_at"])

    op.create_table(
        "dead_letter_task",
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("tenant_id", sa.String(length=32), nullable=False),
        sa.Column("job_id", sa.String(length=26), nullable=False),
        sa.Column("job_type", sa.String(length=64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("error", sa.String(length=1024), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_ai_ci",
    )
    op.create_index("idx_dlq_tenant_status", "dead_letter_task", ["tenant_id", "status", "created_at"])

    op.create_table(
        "idempotency_key",
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("tenant_id", sa.String(length=32), nullable=False),
        sa.Column("key", sa.String(length=128), nullable=False),
        sa.Column("job_id", sa.String(length=26), nullable=False),
        sa.Column("item_id", sa.String(length=64), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "key", name="uk_idempotency_tenant_key"),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_ai_ci",
    )
    op.create_index("idx_idempotency_tenant_job", "idempotency_key", ["tenant_id", "job_id"])

    for trigger, event in (("trg_job_event_no_update", "UPDATE"), ("trg_job_event_no_delete", "DELETE")):
        op.execute(
            f"""
            CREATE TRIGGER {trigger}
            BEFORE {event} ON job_event
            FOR EACH ROW
            SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'job_event is append-only'
            """
        )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_job_event_no_delete")
    op.execute("DROP TRIGGER IF EXISTS trg_job_event_no_update")
    op.drop_index("idx_idempotency_tenant_job", table_name="idempotency_key")
    op.drop_table("idempotency_key")
    op.drop_index("idx_dlq_tenant_status", table_name="dead_letter_task")
    op.drop_table("dead_letter_task")
    op.drop_index("idx_job_event_tenant_job", table_name="job_event")
    op.drop_table("job_event")
    op.drop_index("idx_job_tenant_status", table_name="job")
    op.drop_table("job")
