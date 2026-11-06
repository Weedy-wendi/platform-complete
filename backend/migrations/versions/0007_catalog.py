"""create catalog tables

Revision ID: 0007_catalog
Revises: 0006_artifact
Create Date: 2026-11-05
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "0007_catalog"
down_revision: Union[str, None] = "0006_artifact"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "project",
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("tenant_id", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.String(length=512), nullable=False),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("updated_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("deleted_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("created_by", sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "name", name="uk_project_tenant_name"),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_ai_ci",
    )
    op.create_index("idx_project_tenant_time", "project", ["tenant_id", "updated_at"])

    op.create_table(
        "datasource",
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("tenant_id", sa.String(length=32), nullable=False),
        sa.Column("project_id", sa.String(length=26), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("secret_ref", sa.String(length=256), nullable=True),
        sa.Column("config", sa.JSON(), nullable=False),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("created_by", sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_ai_ci",
    )
    op.create_index("idx_datasource_tenant_project", "datasource", ["tenant_id", "project_id"])

    op.create_table(
        "dataset",
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("tenant_id", sa.String(length=32), nullable=False),
        sa.Column("project_id", sa.String(length=26), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.String(length=512), nullable=False),
        sa.Column("latest_version", sa.Integer(), nullable=False),
        sa.Column("sample_count", sa.Integer(), nullable=False),
        sa.Column("tags", sa.JSON(), nullable=False),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("updated_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("deleted_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("created_by", sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "project_id", "name", name="uk_dataset_tenant_project_name"),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_ai_ci",
    )
    op.create_index("idx_dataset_tenant_time", "dataset", ["tenant_id", "updated_at"])

    op.create_table(
        "dataset_version",
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("tenant_id", sa.String(length=32), nullable=False),
        sa.Column("dataset_id", sa.String(length=26), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False),
        sa.Column("schema_fields", sa.JSON(), nullable=False),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("published_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("created_by", sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "dataset_id", "version", name="uk_version_tenant_dataset_version"),
        sa.UniqueConstraint("tenant_id", "dataset_id", "content_hash", name="uk_version_tenant_dataset_hash"),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_ai_ci",
    )
    op.create_index("idx_version_tenant_dataset", "dataset_version", ["tenant_id", "dataset_id", "version"])

    op.create_table(
        "sample",
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("tenant_id", sa.String(length=32), nullable=False),
        sa.Column("dataset_version_id", sa.String(length=26), nullable=False),
        sa.Column("dataset_id", sa.String(length=26), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("sample_key", sa.String(length=128), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("artifact_id", sa.String(length=26), nullable=True),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dataset_version_id", "sample_key", name="uk_sample_version_key"),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_ai_ci",
    )
    op.create_index("idx_sample_tenant_version", "sample", ["tenant_id", "dataset_version_id", "sample_key"])

    op.create_table(
        "lineage_edge",
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("tenant_id", sa.String(length=32), nullable=False),
        sa.Column("upstream_type", sa.String(length=32), nullable=False),
        sa.Column("upstream_id", sa.String(length=64), nullable=False),
        sa.Column("downstream_type", sa.String(length=32), nullable=False),
        sa.Column("downstream_id", sa.String(length=64), nullable=False),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_ai_ci",
    )
    op.create_index(
        "idx_lineage_tenant_upstream",
        "lineage_edge",
        ["tenant_id", "upstream_type", "upstream_id"],
    )
    op.create_index(
        "idx_lineage_tenant_downstream",
        "lineage_edge",
        ["tenant_id", "downstream_type", "downstream_id"],
    )

    op.execute(
        """
        CREATE TRIGGER trg_dataset_version_immutable
        BEFORE UPDATE ON dataset_version
        FOR EACH ROW
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'dataset_version is immutable'
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_dataset_version_immutable")
    op.drop_index("idx_lineage_tenant_downstream", table_name="lineage_edge")
    op.drop_index("idx_lineage_tenant_upstream", table_name="lineage_edge")
    op.drop_table("lineage_edge")
    op.drop_index("idx_sample_tenant_version", table_name="sample")
    op.drop_table("sample")
    op.drop_index("idx_version_tenant_dataset", table_name="dataset_version")
    op.drop_table("dataset_version")
    op.drop_index("idx_dataset_tenant_time", table_name="dataset")
    op.drop_table("dataset")
    op.drop_index("idx_datasource_tenant_project", table_name="datasource")
    op.drop_table("datasource")
    op.drop_index("idx_project_tenant_time", table_name="project")
    op.drop_table("project")
