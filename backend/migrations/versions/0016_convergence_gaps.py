"""add ingestion transform/dedupe, gateway timeouts and functional dead letters

Revision ID: 0016_convergence_gaps
Revises: 0015_ingestion_dlq
Create Date: 2026-11-05
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "0016_convergence_gaps"
down_revision: Union[str, None] = "0015_ingestion_dlq"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("connector", sa.Column("transform", sa.JSON(), nullable=True))
    op.add_column("connector", sa.Column("dedupe_key", sa.String(length=128), nullable=True))
    op.add_column("ingestion_job", sa.Column("transform", sa.JSON(), nullable=True))
    op.add_column("ingestion_job", sa.Column("dedupe_key", sa.String(length=128), nullable=True))
    op.add_column(
        "provider_config",
        sa.Column("connect_timeout_seconds", sa.Float(), nullable=False, server_default="5.0"),
    )
    op.add_column(
        "provider_config",
        sa.Column("read_timeout_seconds", sa.Float(), nullable=False, server_default="30.0"),
    )
    op.add_column(
        "test_step",
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="1"),
    )

    op.create_table(
        "functional_dead_letter",
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("tenant_id", sa.String(length=32), nullable=False),
        sa.Column("run_id", sa.String(length=26), nullable=False),
        sa.Column("step_id", sa.String(length=26), nullable=False),
        sa.Column("case_id", sa.String(length=26), nullable=False),
        sa.Column("reason", sa.String(length=1024), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("replayed", sa.Boolean(), nullable=False),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "run_id",
            "step_id",
            name="uk_functional_dead_letter_tenant_run_step",
        ),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_ai_ci",
    )
    op.create_index(
        "idx_functional_dead_letter_tenant_created",
        "functional_dead_letter",
        ["tenant_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_functional_dead_letter_tenant_created", table_name="functional_dead_letter")
    op.drop_table("functional_dead_letter")
    op.drop_column("test_step", "attempts")
    op.drop_column("provider_config", "read_timeout_seconds")
    op.drop_column("provider_config", "connect_timeout_seconds")
    op.drop_column("ingestion_job", "dedupe_key")
    op.drop_column("ingestion_job", "transform")
    op.drop_column("connector", "dedupe_key")
    op.drop_column("connector", "transform")
