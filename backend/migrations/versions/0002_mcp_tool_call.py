"""create mcp_tool_call

Revision ID: 0002_mcp_tool_call
Revises: 0001_api_key
Create Date: 2026-11-05
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "0002_mcp_tool_call"
down_revision: Union[str, None] = "0001_api_key"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "mcp_tool_call",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.String(length=32), nullable=False),
        sa.Column("api_key_id", sa.BigInteger(), nullable=False),
        sa.Column("client_name", sa.String(length=128), nullable=True),
        sa.Column("tool_name", sa.String(length=64), nullable=False),
        sa.Column("tool_version", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("result_bytes", sa.Integer(), nullable=False),
        sa.Column("trace_id", sa.String(length=32), nullable=False),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.PrimaryKeyConstraint("id", "created_at", name="pk_mcp_tool_call"),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_ai_ci",
    )
    op.create_index("idx_mcp_call_tenant_time", "mcp_tool_call", ["tenant_id", "created_at"])
    op.create_index("idx_mcp_call_tool_time", "mcp_tool_call", ["tool_name", "created_at"])
    op.create_index("idx_mcp_call_trace", "mcp_tool_call", ["trace_id"])
    # Partitioning is MySQL-specific and kept out of the ORM model.
    op.execute(
        """
        ALTER TABLE mcp_tool_call
        PARTITION BY RANGE COLUMNS(created_at) (
            PARTITION p202611 VALUES LESS THAN ('2026-12-01'),
            PARTITION p202612 VALUES LESS THAN ('2027-01-01'),
            PARTITION pmax VALUES LESS THAN (MAXVALUE)
        )
        """
    )


def downgrade() -> None:
    op.drop_index("idx_mcp_call_trace", table_name="mcp_tool_call")
    op.drop_index("idx_mcp_call_tool_time", table_name="mcp_tool_call")
    op.drop_index("idx_mcp_call_tenant_time", table_name="mcp_tool_call")
    op.drop_table("mcp_tool_call")
