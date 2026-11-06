"""create functional test tables

Revision ID: 0011_functional
Revises: 0010_ingestion
Create Date: 2026-11-05
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "0011_functional"
down_revision: Union[str, None] = "0010_ingestion"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "test_case",
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("tenant_id", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.String(length=512), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("steps", sa.JSON(), nullable=False),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("updated_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("created_by", sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "name", "version", name="uk_test_case_tenant_name_version"),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_ai_ci",
    )
    op.create_index("idx_test_case_tenant_name", "test_case", ["tenant_id", "name", "version"])

    op.create_table(
        "test_suite",
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("tenant_id", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("case_refs", sa.JSON(), nullable=False),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("updated_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("created_by", sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "name", "version", name="uk_test_suite_tenant_name_version"),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_ai_ci",
    )
    op.create_index("idx_test_suite_tenant_name", "test_suite", ["tenant_id", "name", "version"])

    op.create_table(
        "test_run",
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("tenant_id", sa.String(length=32), nullable=False),
        sa.Column("suite_id", sa.String(length=26), nullable=False),
        sa.Column("suite_version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("browser_version", sa.String(length=64), nullable=True),
        sa.Column("error", sa.String(length=1024), nullable=True),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("started_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("finished_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("created_by", sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_ai_ci",
    )
    op.create_index("idx_test_run_tenant_suite", "test_run", ["tenant_id", "suite_id", "created_at"])

    op.create_table(
        "test_step",
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("tenant_id", sa.String(length=32), nullable=False),
        sa.Column("run_id", sa.String(length=26), nullable=False),
        sa.Column("case_id", sa.String(length=26), nullable=False),
        sa.Column("step_index", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("kind", sa.String(length=24), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("assertion", sa.String(length=1024), nullable=True),
        sa.Column("evidence_ref", sa.String(length=64), nullable=True),
        sa.Column("evidence_refs", sa.JSON(), nullable=False),
        sa.Column("error", sa.String(length=1024), nullable=True),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_ai_ci",
    )
    op.create_index("idx_test_step_tenant_run", "test_step", ["tenant_id", "run_id", "step_index"])

    op.create_table(
        "assertion",
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("tenant_id", sa.String(length=32), nullable=False),
        sa.Column("step_id", sa.String(length=26), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("config", sa.JSON(), nullable=False),
        sa.Column("passed", sa.Boolean(), nullable=False),
        sa.Column("expected", sa.JSON(), nullable=False),
        sa.Column("actual", sa.JSON(), nullable=False),
        sa.Column("message", sa.String(length=512), nullable=False),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_ai_ci",
    )
    op.create_index("idx_assertion_tenant_step", "assertion", ["tenant_id", "step_id"])

    op.create_table(
        "visual_diff",
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("tenant_id", sa.String(length=32), nullable=False),
        sa.Column("run_id", sa.String(length=26), nullable=True),
        sa.Column("step_id", sa.String(length=26), nullable=True),
        sa.Column("expected_ref", sa.String(length=64), nullable=False),
        sa.Column("actual_ref", sa.String(length=64), nullable=False),
        sa.Column("diff_ref", sa.String(length=64), nullable=True),
        sa.Column("threshold", sa.Float(), nullable=False),
        sa.Column("mismatch_ratio", sa.Float(), nullable=False),
        sa.Column("passed", sa.Boolean(), nullable=False),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_ai_ci",
    )
    op.create_index("idx_visual_diff_tenant_run", "visual_diff", ["tenant_id", "run_id"])


def downgrade() -> None:
    op.drop_index("idx_visual_diff_tenant_run", table_name="visual_diff")
    op.drop_table("visual_diff")
    op.drop_index("idx_assertion_tenant_step", table_name="assertion")
    op.drop_table("assertion")
    op.drop_index("idx_test_step_tenant_run", table_name="test_step")
    op.drop_table("test_step")
    op.drop_index("idx_test_run_tenant_suite", table_name="test_run")
    op.drop_table("test_run")
    op.drop_index("idx_test_suite_tenant_name", table_name="test_suite")
    op.drop_table("test_suite")
    op.drop_index("idx_test_case_tenant_name", table_name="test_case")
    op.drop_table("test_case")
