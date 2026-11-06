"""create gate tables

Revision ID: 0013_gate
Revises: 0012_evaluation
Create Date: 2026-11-05
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "0013_gate"
down_revision: Union[str, None] = "0012_evaluation"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "gate",
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("tenant_id", sa.String(length=32), nullable=False),
        sa.Column("suite_id", sa.String(length=26), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.String(length=512), nullable=False),
        sa.Column("rules_version", sa.Integer(), nullable=False),
        sa.Column("baseline_run_id", sa.String(length=26), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("updated_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("created_by", sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "suite_id", "name", name="uk_gate_tenant_suite_name"),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_ai_ci",
    )
    op.create_index("idx_gate_tenant_suite", "gate", ["tenant_id", "suite_id"])

    op.create_table(
        "gate_rule",
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("tenant_id", sa.String(length=32), nullable=False),
        sa.Column("gate_id", sa.String(length=26), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("kind", sa.String(length=24), nullable=False),
        sa.Column("metric", sa.String(length=128), nullable=False),
        sa.Column("operator", sa.String(length=8), nullable=False),
        sa.Column("threshold", sa.Float(), nullable=False),
        sa.Column("baseline_run_id", sa.String(length=26), nullable=True),
        sa.Column("min_samples", sa.Integer(), nullable=True),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("gate_id", "name", name="uk_gate_rule_gate_name"),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_ai_ci",
    )
    op.create_index("idx_gate_rule_tenant_gate", "gate_rule", ["tenant_id", "gate_id"])

    op.create_table(
        "gate_result",
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("tenant_id", sa.String(length=32), nullable=False),
        sa.Column("gate_id", sa.String(length=26), nullable=False),
        sa.Column("suite_id", sa.String(length=26), nullable=False),
        sa.Column("run_id", sa.String(length=26), nullable=False),
        sa.Column("manifest_hash", sa.String(length=64), nullable=False),
        sa.Column("passed", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("rules", sa.JSON(), nullable=False),
        sa.Column("evaluated_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_ai_ci",
    )
    op.create_index(
        "idx_gate_result_tenant_suite_run",
        "gate_result",
        ["tenant_id", "suite_id", "run_id", "evaluated_at"],
    )
    op.create_index(
        "idx_gate_result_tenant_gate_run",
        "gate_result",
        ["tenant_id", "gate_id", "run_id", "evaluated_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_gate_result_tenant_gate_run", table_name="gate_result")
    op.drop_index("idx_gate_result_tenant_suite_run", table_name="gate_result")
    op.drop_table("gate_result")
    op.drop_index("idx_gate_rule_tenant_gate", table_name="gate_rule")
    op.drop_table("gate_rule")
    op.drop_index("idx_gate_tenant_suite", table_name="gate")
    op.drop_table("gate")
