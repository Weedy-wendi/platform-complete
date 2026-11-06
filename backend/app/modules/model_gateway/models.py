"""Model gateway models: provider config and immutable call records."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.clock import utcnow_naive
from app.core.db import Base


class ProviderConfig(Base):
    __tablename__ = "provider_config"

    id: Mapped[str] = mapped_column(String(26), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    secret_ref: Mapped[str] = mapped_column(String(256), nullable=False)
    base_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    timeout_seconds: Mapped[float] = mapped_column(Float, nullable=False, default=30.0)
    connect_timeout_seconds: Mapped[float] = mapped_column(Float, nullable=False, default=5.0)
    read_timeout_seconds: Mapped[float] = mapped_column(Float, nullable=False, default=30.0)
    max_retries: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    input_cost_per_million: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    output_cost_per_million: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False, default=utcnow_naive)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), nullable=False, default=utcnow_naive, onupdate=utcnow_naive
    )

    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uk_provider_tenant_name"),
        Index("idx_provider_tenant_enabled", "tenant_id", "enabled"),
    )


class ModelCall(Base):
    __tablename__ = "model_call"

    id: Mapped[str] = mapped_column(String(26), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(32), nullable=False)
    provider_config_id: Mapped[str] = mapped_column(String(26), nullable=False)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    prompt_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    trace_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    raw_ref: Mapped[str | None] = mapped_column(String(256), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False, default=utcnow_naive)

    __table_args__ = (
        Index("idx_model_call_tenant_time", "tenant_id", "created_at"),
        Index("idx_model_call_tenant_provider", "tenant_id", "provider", "model"),
    )
