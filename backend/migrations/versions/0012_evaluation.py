"""create evaluation tables

Revision ID: 0012_evaluation
Revises: 0011_functional
Create Date: 2026-11-05
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "0012_evaluation"
down_revision: Union[str, None] = "0011_functional"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _dt() -> mysql.DATETIME:
    return mysql.DATETIME(fsp=6)


def _table(name: str, *columns: sa.Column) -> None:
    op.create_table(
        name,
        *columns,
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_ai_ci",
    )


def upgrade() -> None:
    _table(
        "evaluator",
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("tenant_id", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.String(length=512), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("latest_version", sa.Integer(), nullable=False),
        sa.Column("created_at", _dt(), nullable=False),
        sa.Column("created_by", sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "name", name="uk_evaluator_tenant_name"),
    )
    op.create_index("idx_evaluator_tenant_kind", "evaluator", ["tenant_id", "kind"])

    _table(
        "evaluator_version",
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("tenant_id", sa.String(length=32), nullable=False),
        sa.Column("evaluator_id", sa.String(length=26), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("config", sa.JSON(), nullable=False),
        sa.Column("config_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", _dt(), nullable=False),
        sa.Column("created_by", sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id", "evaluator_id", "version", name="uk_eval_version_tenant_evaluator_version"
        ),
    )
    op.create_index(
        "idx_eval_version_tenant_evaluator",
        "evaluator_version",
        ["tenant_id", "evaluator_id", "version"],
    )

    _table(
        "metric",
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("tenant_id", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.String(length=512), nullable=False),
        sa.Column("direction", sa.String(length=32), nullable=False),
        sa.Column("evaluator_id", sa.String(length=26), nullable=True),
        sa.Column("created_at", _dt(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "name", name="uk_metric_tenant_name"),
    )
    op.create_index("idx_metric_tenant_direction", "metric", ["tenant_id", "direction"])

    _table(
        "eval_suite",
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("tenant_id", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.String(length=512), nullable=False),
        sa.Column("latest_version", sa.Integer(), nullable=False),
        sa.Column("created_at", _dt(), nullable=False),
        sa.Column("updated_at", _dt(), nullable=False),
        sa.Column("created_by", sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "name", name="uk_suite_tenant_name"),
    )

    _table(
        "suite_version",
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("tenant_id", sa.String(length=32), nullable=False),
        sa.Column("suite_id", sa.String(length=26), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("evaluator_versions", sa.JSON(), nullable=False),
        sa.Column("metric_configs", sa.JSON(), nullable=False),
        sa.Column("created_at", _dt(), nullable=False),
        sa.Column("created_by", sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "suite_id", "version", name="uk_suite_version_tenant_suite_version"),
    )

    _table(
        "target",
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("tenant_id", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("adapter", sa.String(length=64), nullable=False),
        sa.Column("adapter_version", sa.String(length=32), nullable=False),
        sa.Column("config_version", sa.String(length=32), nullable=False),
        sa.Column("config", sa.JSON(), nullable=False),
        sa.Column("created_at", _dt(), nullable=False),
        sa.Column("created_by", sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "name",
            "config_version",
            "adapter_version",
            name="uk_target_tenant_name_versions",
        ),
    )

    _table(
        "run",
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("tenant_id", sa.String(length=32), nullable=False),
        sa.Column("client_request_id", sa.String(length=128), nullable=False),
        sa.Column("suite_id", sa.String(length=26), nullable=True),
        sa.Column("suite_version", sa.Integer(), nullable=True),
        sa.Column("dataset_id", sa.String(length=26), nullable=False),
        sa.Column("dataset_version", sa.Integer(), nullable=False),
        sa.Column("dataset_hash", sa.String(length=64), nullable=False),
        sa.Column("manifest", sa.JSON(), nullable=False),
        sa.Column("manifest_hash", sa.String(length=64), nullable=False),
        sa.Column("mode", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("total_items", sa.Integer(), nullable=False),
        sa.Column("succeeded_items", sa.Integer(), nullable=False),
        sa.Column("failed_items", sa.Integer(), nullable=False),
        sa.Column("skipped_items", sa.Integer(), nullable=False),
        sa.Column("progress", sa.Integer(), nullable=False),
        sa.Column("cost_usd", sa.Float(), nullable=False),
        sa.Column("budget_usd", sa.Float(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", _dt(), nullable=False),
        sa.Column("started_at", _dt(), nullable=True),
        sa.Column("finished_at", _dt(), nullable=True),
        sa.Column("created_by", sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "client_request_id", name="uk_run_tenant_client_request"),
    )
    op.create_index("idx_run_tenant_status", "run", ["tenant_id", "status", "created_at"])
    op.create_index("idx_run_tenant_manifest", "run", ["tenant_id", "manifest_hash"])

    _table(
        "run_item",
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("tenant_id", sa.String(length=32), nullable=False),
        sa.Column("run_id", sa.String(length=26), nullable=False),
        sa.Column("sample_key", sa.String(length=128), nullable=False),
        sa.Column("sample_index", sa.Integer(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("expected", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("output", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("cost_usd", sa.Float(), nullable=False),
        sa.Column("raw_ref", sa.String(length=512), nullable=True),
        sa.Column("trace_id", sa.String(length=64), nullable=True),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("created_at", _dt(), nullable=False),
        sa.Column("updated_at", _dt(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "sample_key", name="uk_run_item_run_sample"),
    )
    op.create_index("idx_run_item_tenant_run", "run_item", ["tenant_id", "run_id", "sample_index"])
    op.create_index("idx_run_item_tenant_status", "run_item", ["tenant_id", "run_id", "status"])

    _table(
        "score",
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("tenant_id", sa.String(length=32), nullable=False),
        sa.Column("run_id", sa.String(length=26), nullable=False),
        sa.Column("run_item_id", sa.String(length=26), nullable=False),
        sa.Column("metric_name", sa.String(length=128), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("passed", sa.Boolean(), nullable=True),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("evaluator_version_id", sa.String(length=26), nullable=True),
        sa.Column("judge_call_id", sa.String(length=26), nullable=True),
        sa.Column("created_at", _dt(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_item_id", "metric_name", name="uk_score_item_metric"),
    )
    op.create_index("idx_score_tenant_run_metric", "score", ["tenant_id", "run_id", "metric_name"])

    _table(
        "judge_call",
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("tenant_id", sa.String(length=32), nullable=False),
        sa.Column("run_id", sa.String(length=26), nullable=False),
        sa.Column("run_item_id", sa.String(length=26), nullable=False),
        sa.Column("evaluator_version_id", sa.String(length=26), nullable=True),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("prompt_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("request", sa.JSON(), nullable=False),
        sa.Column("response", sa.JSON(), nullable=False),
        sa.Column("parsed", sa.JSON(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("cost_usd", sa.Float(), nullable=False),
        sa.Column("raw_ref", sa.String(length=512), nullable=True),
        sa.Column("created_at", _dt(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_judge_call_tenant_run", "judge_call", ["tenant_id", "run_id", "created_at"])

    _table(
        "baseline",
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("tenant_id", sa.String(length=32), nullable=False),
        sa.Column("suite_id", sa.String(length=26), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("run_id", sa.String(length=26), nullable=False),
        sa.Column("manifest_hash", sa.String(length=64), nullable=False),
        sa.Column("frozen", sa.Boolean(), nullable=False),
        sa.Column("created_at", _dt(), nullable=False),
        sa.Column("created_by", sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "suite_id", "name", name="uk_baseline_tenant_suite_name"),
    )
    op.create_index("idx_baseline_tenant_suite", "baseline", ["tenant_id", "suite_id"])


def downgrade() -> None:
    op.drop_index("idx_baseline_tenant_suite", table_name="baseline")
    op.drop_table("baseline")
    op.drop_index("idx_judge_call_tenant_run", table_name="judge_call")
    op.drop_table("judge_call")
    op.drop_index("idx_score_tenant_run_metric", table_name="score")
    op.drop_table("score")
    op.drop_index("idx_run_item_tenant_status", table_name="run_item")
    op.drop_index("idx_run_item_tenant_run", table_name="run_item")
    op.drop_table("run_item")
    op.drop_index("idx_run_tenant_manifest", table_name="run")
    op.drop_index("idx_run_tenant_status", table_name="run")
    op.drop_table("run")
    op.drop_table("target")
    op.drop_table("suite_version")
    op.drop_table("eval_suite")
    op.drop_index("idx_metric_tenant_direction", table_name="metric")
    op.drop_table("metric")
    op.drop_index("idx_eval_version_tenant_evaluator", table_name="evaluator_version")
    op.drop_table("evaluator_version")
    op.drop_index("idx_evaluator_tenant_kind", table_name="evaluator")
    op.drop_table("evaluator")
