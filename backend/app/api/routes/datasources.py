"""Datasource CRUD (017-rest-api FR-006)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, status

from app.api.deps import get_datasources, get_tenant_context, require_scope
from app.api.ports import DatasourcesPort
from app.api.schemas import (
    DatasourceCreate,
    DatasourceOut,
    DatasourcePage,
    DatasourceUpdate,
)
from app.core.context import Principal, TenantContext

router = APIRouter(prefix="/datasources", tags=["datasources"])


@router.get("", response_model=DatasourcePage)
def list_datasources(
    ctx: Annotated[TenantContext, Depends(get_tenant_context)],
    services: Annotated[DatasourcesPort, Depends(get_datasources)],
    _: Annotated[Principal, Depends(require_scope("datasources:read"))],
    cursor: Annotated[str | None, Query(max_length=512)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> DatasourcePage:
    page = services.list_datasources(ctx, cursor=cursor, limit=limit)
    return DatasourcePage(
        items=[DatasourceOut.from_record(record) for record in page.items],
        next_cursor=page.next_cursor,
    )


@router.post("", response_model=DatasourceOut, status_code=status.HTTP_201_CREATED)
def create_datasource(
    payload: DatasourceCreate,
    ctx: Annotated[TenantContext, Depends(get_tenant_context)],
    services: Annotated[DatasourcesPort, Depends(get_datasources)],
    _: Annotated[Principal, Depends(require_scope("datasources:write"))],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key", max_length=128)] = None,
) -> DatasourceOut:
    record = services.create_datasource(
        ctx,
        name=payload.name,
        description=payload.description,
        kind=payload.kind,
        config=payload.config,
        idempotency_key=idempotency_key,
    )
    return DatasourceOut.from_record(record)


@router.get("/{datasource_id}", response_model=DatasourceOut)
def get_datasource(
    datasource_id: str,
    ctx: Annotated[TenantContext, Depends(get_tenant_context)],
    services: Annotated[DatasourcesPort, Depends(get_datasources)],
    _: Annotated[Principal, Depends(require_scope("datasources:read"))],
) -> DatasourceOut:
    return DatasourceOut.from_record(services.get_datasource(ctx, datasource_id))


@router.patch("/{datasource_id}", response_model=DatasourceOut)
def update_datasource(
    datasource_id: str,
    payload: DatasourceUpdate,
    ctx: Annotated[TenantContext, Depends(get_tenant_context)],
    services: Annotated[DatasourcesPort, Depends(get_datasources)],
    _: Annotated[Principal, Depends(require_scope("datasources:write"))],
) -> DatasourceOut:
    record = services.update_datasource(
        ctx,
        datasource_id,
        name=payload.name,
        description=payload.description,
        kind=payload.kind,
        config=payload.config,
    )
    return DatasourceOut.from_record(record)


@router.delete("/{datasource_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_datasource(
    datasource_id: str,
    ctx: Annotated[TenantContext, Depends(get_tenant_context)],
    services: Annotated[DatasourcesPort, Depends(get_datasources)],
    _: Annotated[Principal, Depends(require_scope("datasources:write"))],
) -> None:
    services.delete_datasource(ctx, datasource_id)


__all__ = ["router"]
