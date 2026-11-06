"""create identity tables

Revision ID: 0003_identity
Revises: 0002_mcp_tool_call
Create Date: 2026-11-05
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "0003_identity"
down_revision: Union[str, None] = "0002_mcp_tool_call"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_AUDIT_COLUMNS = (
    sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
    sa.Column("updated_at", mysql.DATETIME(fsp=6), nullable=False),
    sa.Column("deleted_at", mysql.DATETIME(fsp=6), nullable=True),
    sa.Column("created_by", sa.String(length=64), nullable=False),
    sa.Column("updated_by", sa.String(length=64), nullable=True),
)


def upgrade() -> None:
    op.create_table(
        "tenant",
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("slug", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        *_AUDIT_COLUMNS,
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug", name="uk_tenant_slug"),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_ai_ci",
    )
    op.create_index("idx_tenant_status", "tenant", ["status", "deleted_at"])

    op.create_table(
        "user",
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("tenant_id", sa.String(length=32), nullable=False),
        sa.Column("email", sa.String(length=254), nullable=False),
        sa.Column("display_name", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        *_AUDIT_COLUMNS,
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "email", name="uk_user_tenant_email"),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_ai_ci",
    )
    op.create_index("idx_user_tenant_status", "user", ["tenant_id", "status", "deleted_at"])

    op.create_table(
        "role",
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("tenant_id", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=False),
        sa.Column("is_system", sa.Boolean(), nullable=False),
        *_AUDIT_COLUMNS,
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "name", name="uk_role_tenant_name"),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_ai_ci",
    )
    op.create_index("idx_role_tenant", "role", ["tenant_id", "deleted_at"])

    op.create_table(
        "permission",
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("tenant_id", sa.String(length=32), nullable=False),
        sa.Column("code", sa.String(length=96), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=False),
        *_AUDIT_COLUMNS,
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "code", name="uk_permission_tenant_code"),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_ai_ci",
    )
    op.create_index("idx_permission_tenant", "permission", ["tenant_id", "deleted_at"])

    op.create_table(
        "user_role",
        sa.Column("tenant_id", sa.String(length=32), nullable=False),
        sa.Column("user_id", sa.String(length=26), nullable=False),
        sa.Column("role_id", sa.String(length=26), nullable=False),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("created_by", sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint("tenant_id", "user_id", "role_id"),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_ai_ci",
    )
    op.create_index("idx_user_role_tenant_user", "user_role", ["tenant_id", "user_id"])
    op.create_index("idx_user_role_tenant_role", "user_role", ["tenant_id", "role_id"])

    op.create_table(
        "role_permission",
        sa.Column("tenant_id", sa.String(length=32), nullable=False),
        sa.Column("role_id", sa.String(length=26), nullable=False),
        sa.Column("permission_id", sa.String(length=26), nullable=False),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("created_by", sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint("tenant_id", "role_id", "permission_id"),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_ai_ci",
    )
    op.create_index("idx_role_permission_tenant_role", "role_permission", ["tenant_id", "role_id"])
    op.create_index(
        "idx_role_permission_tenant_permission",
        "role_permission",
        ["tenant_id", "permission_id"],
    )


def downgrade() -> None:
    op.drop_index("idx_role_permission_tenant_permission", table_name="role_permission")
    op.drop_index("idx_role_permission_tenant_role", table_name="role_permission")
    op.drop_table("role_permission")
    op.drop_index("idx_user_role_tenant_role", table_name="user_role")
    op.drop_index("idx_user_role_tenant_user", table_name="user_role")
    op.drop_table("user_role")
    op.drop_index("idx_permission_tenant", table_name="permission")
    op.drop_table("permission")
    op.drop_index("idx_role_tenant", table_name="role")
    op.drop_table("role")
    op.drop_index("idx_user_tenant_status", table_name="user")
    op.drop_table("user")
    op.drop_index("idx_tenant_status", table_name="tenant")
    op.drop_table("tenant")
