"""Tenant-scoped repository base.

Every query issued through this base carries the current tenant id, so a missing
context or a cross-tenant lookup fails before SQL reaches the database.
"""

from __future__ import annotations

from typing import Any, TypeVar

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.core.context import get_tenant_context
from app.core.errors import TenantRequiredError

ModelT = TypeVar("ModelT")


class TenantScopedRepository:
    def __init__(self, session: Session, tenant_id: str | None = None) -> None:
        resolved = tenant_id or get_tenant_context().tenant_id
        if not resolved:
            raise TenantRequiredError("tenant_id is required")
        self.session = session
        self.tenant_id = resolved

    def scoped(self, model: type[Any]) -> Select[Any]:
        if not hasattr(model, "tenant_id"):
            raise TypeError(f"{model.__name__} has no tenant_id column")
        return select(model).where(model.tenant_id == self.tenant_id)

    def get(self, model: type[ModelT], entity_id: Any) -> ModelT | None:
        if not hasattr(model, "id"):
            raise TypeError(f"{model.__name__} has no id column")
        statement = self.scoped(model).where(model.id == entity_id)  # type: ignore[attr-defined]
        return self.session.scalar(statement)

    def list(self, model: type[ModelT]) -> list[ModelT]:
        return list(self.session.scalars(self.scoped(model)))

    def add(self, entity: ModelT) -> ModelT:
        entity_tenant = getattr(entity, "tenant_id", None)
        if entity_tenant != self.tenant_id:
            raise ValueError("entity tenant_id does not match repository tenant")
        self.session.add(entity)
        return entity
