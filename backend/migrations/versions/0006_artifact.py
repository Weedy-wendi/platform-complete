"""create artifact metadata

Revision ID: 0006_artifact
Revises: 0005_audit_partitions
Create Date: 2026-11-05
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "0006_artifact"
down_revision: Union[str, None] = "0005_audit_partitions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "artifact",
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("tenant_id", sa.String(length=32), nullable=False),
        sa.Column("asset_type", sa.String(length=64), nullable=False),
        sa.Column("asset_id", sa.String(length=64), nullable=False),
        sa.Column("version", sa.String(length=32), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("s3_key", sa.String(length=512), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("mime_type", sa.String(length=128), nullable=False),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("created_by", sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("s3_key", name="uk_artifact_s3_key"),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_ai_ci",
    )
    op.create_index("idx_artifact_tenant_asset", "artifact", ["tenant_id", "asset_type", "asset_id"])
    op.create_index("idx_artifact_tenant_time", "artifact", ["tenant_id", "created_at"])


def downgrade() -> None:
    op.drop_index("idx_artifact_tenant_time", table_name="artifact")
    op.drop_index("idx_artifact_tenant_asset", table_name="artifact")
    op.drop_table("artifact")
