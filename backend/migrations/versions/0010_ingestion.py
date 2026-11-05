"""create ingestion tables

Revision ID: 0010_ingestion
Revises: 0009_model_gateway
Create Date: 2026-11-05
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "0010_ingestion"
down_revision: Union[str, None] = "0009_model_gateway"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _audit_columns() -> list[sa.Column]:
    return [
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("updated_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("created_by", sa.String(length=64), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "connector",
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("tenant_id", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("config", sa.JSON(), nullable=False),
        sa.Column("secret_ref", sa.String(length=256), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False),
        *_audit_columns(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "name", name="uk_connector_tenant_name"),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_ai_ci",
    )
    op.create_index("idx_connector_tenant_kind", "connector", ["tenant_id", "kind"])

    op.create_table(
        "ingestion_job",
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("tenant_id", sa.String(length=32), nullable=False),
        sa.Column("connector_id", sa.String(length=26), nullable=False),
        sa.Column("dataset_id", sa.String(length=26), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("idempotency_key", sa.String(length=160), nullable=False),
        sa.Column("rows_read", sa.Integer(), nullable=False),
        sa.Column("rows_written", sa.Integer(), nullable=False),
        sa.Column("rows_skipped", sa.Integer(), nullable=False),
        sa.Column("cursor_value", sa.String(length=256), nullable=True),
        sa.Column("schema_drift", sa.JSON(), nullable=False),
        sa.Column("error", sa.String(length=1024), nullable=True),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("updated_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("started_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("finished_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("created_by", sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "idempotency_key", name="uk_ingestion_job_tenant_idem"),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_ai_ci",
    )
    op.create_index(
        "idx_ingestion_job_tenant_status",
        "ingestion_job",
        ["tenant_id", "status", "updated_at"],
    )

    op.create_table(
        "sync_cursor",
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("tenant_id", sa.String(length=32), nullable=False),
        sa.Column("connector_id", sa.String(length=26), nullable=False),
        sa.Column("dataset_id", sa.String(length=26), nullable=False),
        sa.Column("value", sa.String(length=256), nullable=True),
        sa.Column("schema_fields", sa.JSON(), nullable=False),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("updated_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "connector_id",
            "dataset_id",
            name="uk_sync_cursor_tenant_connector_dataset",
        ),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_ai_ci",
    )

    op.create_table(
        "quality_rule",
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("tenant_id", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("rule_type", sa.String(length=32), nullable=False),
        sa.Column("config", sa.JSON(), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        *_audit_columns(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "name", name="uk_quality_rule_tenant_name"),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_ai_ci",
    )
    op.create_index("idx_quality_rule_tenant_enabled", "quality_rule", ["tenant_id", "enabled"])

    op.create_table(
        "quality_result",
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("tenant_id", sa.String(length=32), nullable=False),
        sa.Column("job_id", sa.String(length=26), nullable=False),
        sa.Column("rule_id", sa.String(length=26), nullable=True),
        sa.Column("dataset_id", sa.String(length=26), nullable=True),
        sa.Column("passed", sa.Boolean(), nullable=False),
        sa.Column("checked_rows", sa.Integer(), nullable=False),
        sa.Column("failed_rows", sa.Integer(), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_ai_ci",
    )
    op.create_index(
        "idx_quality_result_tenant_job",
        "quality_result",
        ["tenant_id", "job_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_quality_result_tenant_job", table_name="quality_result")
    op.drop_table("quality_result")
    op.drop_index("idx_quality_rule_tenant_enabled", table_name="quality_rule")
    op.drop_table("quality_rule")
    op.drop_table("sync_cursor")
    op.drop_index("idx_ingestion_job_tenant_status", table_name="ingestion_job")
    op.drop_table("ingestion_job")
    op.drop_index("idx_connector_tenant_kind", table_name="connector")
    op.drop_table("connector")
