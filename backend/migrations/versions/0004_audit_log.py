"""create audit_log

Revision ID: 0004_audit_log
Revises: 0003_identity
Create Date: 2026-11-05
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "0004_audit_log"
down_revision: Union[str, None] = "0003_identity"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "audit_log",
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("tenant_id", sa.String(length=32), nullable=False),
        sa.Column("actor_id", sa.String(length=64), nullable=False),
        sa.Column("action", sa.String(length=96), nullable=False),
        sa.Column("resource_type", sa.String(length=64), nullable=False),
        sa.Column("resource_id", sa.String(length=96), nullable=False),
        sa.Column("trace_id", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("detail", sa.JSON(), nullable=False),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_ai_ci",
    )
    op.create_index("idx_audit_log_tenant_time", "audit_log", ["tenant_id", "created_at"])
    op.create_index("idx_audit_log_actor", "audit_log", ["tenant_id", "actor_id", "created_at"])
    op.create_index(
        "idx_audit_log_resource",
        "audit_log",
        ["tenant_id", "resource_type", "resource_id"],
    )
    op.create_index("idx_audit_log_trace", "audit_log", ["trace_id"])


def downgrade() -> None:
    op.drop_index("idx_audit_log_trace", table_name="audit_log")
    op.drop_index("idx_audit_log_resource", table_name="audit_log")
    op.drop_index("idx_audit_log_actor", table_name="audit_log")
    op.drop_index("idx_audit_log_tenant_time", table_name="audit_log")
    op.drop_table("audit_log")
