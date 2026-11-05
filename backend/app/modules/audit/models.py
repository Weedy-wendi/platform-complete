"""Audit SQLAlchemy models."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, BigInteger, DateTime, Index, Integer, PrimaryKeyConstraint, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class McpToolCall(Base):
    __tablename__ = "mcp_tool_call"

    id: Mapped[int] = mapped_column(BigInteger, autoincrement=True, nullable=False)
    tenant_id: Mapped[str] = mapped_column(String(32), nullable=False)
    api_key_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    client_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    tool_name: Mapped[str] = mapped_column(String(64), nullable=False)
    tool_version: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    result_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    trace_id: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)

    __table_args__ = (
        PrimaryKeyConstraint("id", "created_at", name="pk_mcp_tool_call"),
        Index("idx_mcp_call_tenant_time", "tenant_id", "created_at"),
        Index("idx_mcp_call_tool_time", "tool_name", "created_at"),
        Index("idx_mcp_call_trace", "trace_id"),
    )


class AuditLog(Base):
    """Generic append-only audit record for platform security events."""

    __tablename__ = "audit_log"

    id: Mapped[str] = mapped_column(String(26), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(32), nullable=False)
    actor_id: Mapped[str] = mapped_column(String(64), nullable=False)
    action: Mapped[str] = mapped_column(String(96), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_id: Mapped[str] = mapped_column(String(96), nullable=False)
    trace_id: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    detail: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), primary_key=True)

    __table_args__ = (
        Index("idx_audit_log_tenant_time", "tenant_id", "created_at"),
        Index("idx_audit_log_actor", "tenant_id", "actor_id", "created_at"),
        Index("idx_audit_log_resource", "tenant_id", "resource_type", "resource_id"),
        Index("idx_audit_log_trace", "trace_id"),
    )
