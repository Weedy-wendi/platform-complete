"""Target configuration routes (017-rest-api FR-008)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import get_targets, get_tenant_context, require_scope
from app.api.ports import TargetsPort
from app.api.schemas import ConfigCreate, ConfigOut, ConfigPage
from app.core.context import Principal, TenantContext

router = APIRouter(prefix="/targets", tags=["targets"])


@router.get("", response_model=ConfigPage)
def list_targets(
    ctx: Annotated[TenantContext, Depends(get_tenant_context)],
    services: Annotated[TargetsPort, Depends(get_targets)],
    _: Annotated[Principal, Depends(require_scope("evaluators:read"))],
    cursor: Annotated[str | None, Query(max_length=512)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> ConfigPage:
    page = services.list_targets(ctx, cursor=cursor, limit=limit)
    return ConfigPage(
        items=[ConfigOut.from_record(record) for record in page.items],
        next_cursor=page.next_cursor,
    )


@router.post("", response_model=ConfigOut, status_code=status.HTTP_201_CREATED)
def create_target(
    payload: ConfigCreate,
    ctx: Annotated[TenantContext, Depends(get_tenant_context)],
    services: Annotated[TargetsPort, Depends(get_targets)],
    _: Annotated[Principal, Depends(require_scope("evaluators:write"))],
) -> ConfigOut:
    record = services.create_target(
        ctx,
        name=payload.name,
        description=payload.description,
        config=payload.config,
    )
    return ConfigOut.from_record(record)


@router.get("/{target_id}", response_model=ConfigOut)
def get_target(
    target_id: str,
    ctx: Annotated[TenantContext, Depends(get_tenant_context)],
    services: Annotated[TargetsPort, Depends(get_targets)],
    _: Annotated[Principal, Depends(require_scope("evaluators:read"))],
) -> ConfigOut:
    return ConfigOut.from_record(services.get_target(ctx, target_id))


__all__ = ["router"]
