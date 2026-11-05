"""create ingestion dead letter table

Revision ID: 0015_ingestion_dlq
Revises: 0014_reporting
Create Date: 2026-11-05
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "0015_ingestion_dlq"
down_revision: Union[str, None] = "0014_reporting"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ingestion_dead_letter",
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("tenant_id", sa.String(length=32), nullable=False),
        sa.Column("job_id", sa.String(length=26), nullable=False),
        sa.Column("connector_id", sa.String(length=26), nullable=False),
        sa.Column("reason", sa.String(length=1024), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("replayed", sa.Boolean(), nullable=False),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "job_id",
            name="uk_ingestion_dead_letter_tenant_job",
        ),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_ai_ci",
    )
    op.create_index(
        "idx_ingestion_dead_letter_tenant_created",
        "ingestion_dead_letter",
        ["tenant_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_ingestion_dead_letter_tenant_created", table_name="ingestion_dead_letter")
    op.drop_table("ingestion_dead_letter")
