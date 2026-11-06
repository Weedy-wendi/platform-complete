"""Identity SQLAlchemy models."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    Index,
    LargeBinary,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.clock import utcnow_naive
from app.core.db import Base


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False, default=utcnow_naive)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), nullable=False, default=utcnow_naive, onupdate=utcnow_naive
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    created_by: Mapped[str] = mapped_column(String(64), nullable=False, default="system")
    updated_by: Mapped[str | None] = mapped_column(String(64), nullable=True)


class Tenant(TimestampMixin, Base):
    __tablename__ = "tenant"

    id: Mapped[str] = mapped_column(String(26), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    slug: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")

    __table_args__ = (Index("idx_tenant_status", "status", "deleted_at"),)


class User(TimestampMixin, Base):
    __tablename__ = "user"

    id: Mapped[str] = mapped_column(String(26), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(32), nullable=False)
    email: Mapped[str] = mapped_column(String(254), nullable=False)
    display_name: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")

    __table_args__ = (
        UniqueConstraint("tenant_id", "email", name="uk_user_tenant_email"),
        Index("idx_user_tenant_status", "tenant_id", "status", "deleted_at"),
    )


class Role(TimestampMixin, Base):
    __tablename__ = "role"

    id: Mapped[str] = mapped_column(String(26), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    is_system: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uk_role_tenant_name"),
        Index("idx_role_tenant", "tenant_id", "deleted_at"),
    )


class Permission(TimestampMixin, Base):
    __tablename__ = "permission"

    id: Mapped[str] = mapped_column(String(26), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(32), nullable=False)
    code: Mapped[str] = mapped_column(String(96), nullable=False)
    description: Mapped[str] = mapped_column(String(255), nullable=False, default="")

    __table_args__ = (
        UniqueConstraint("tenant_id", "code", name="uk_permission_tenant_code"),
        Index("idx_permission_tenant", "tenant_id", "deleted_at"),
    )


class UserRole(Base):
    __tablename__ = "user_role"

    tenant_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(26), primary_key=True)
    role_id: Mapped[str] = mapped_column(String(26), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False, default=utcnow_naive)
    created_by: Mapped[str] = mapped_column(String(64), nullable=False, default="system")

    __table_args__ = (
        Index("idx_user_role_tenant_user", "tenant_id", "user_id"),
        Index("idx_user_role_tenant_role", "tenant_id", "role_id"),
    )


class RolePermission(Base):
    __tablename__ = "role_permission"

    tenant_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    role_id: Mapped[str] = mapped_column(String(26), primary_key=True)
    permission_id: Mapped[str] = mapped_column(String(26), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False, default=utcnow_naive)
    created_by: Mapped[str] = mapped_column(String(64), nullable=False, default="system")

    __table_args__ = (
        Index("idx_role_permission_tenant_role", "tenant_id", "role_id"),
        Index("idx_role_permission_tenant_permission", "tenant_id", "permission_id"),
    )


class ApiKey(Base):
    __tablename__ = "api_key"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String(32), nullable=False)
    key_id: Mapped[str] = mapped_column(String(24), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    secret_hmac: Mapped[bytes] = mapped_column(LargeBinary(32), nullable=False)
    scopes: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    created_by: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)

    __table_args__ = (
        Index("idx_api_key_tenant", "tenant_id", "revoked_at"),
        Index("idx_api_key_expires", "expires_at"),
    )
