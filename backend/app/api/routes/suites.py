"""Suite configuration routes (017-rest-api FR-008)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import get_suites, get_tenant_context, require_scope
from app.api.ports import SuitesPort
from app.api.schemas import ConfigCreate, ConfigOut, ConfigPage
from app.core.context import Principal, TenantContext

router = APIRouter(prefix="/suites", tags=["suites"])


@router.get("", response_model=ConfigPage)
def list_suites(
    ctx: Annotated[TenantContext, Depends(get_tenant_context)],
    services: Annotated[SuitesPort, Depends(get_suites)],
    _: Annotated[Principal, Depends(require_scope("evaluators:read"))],
    cursor: Annotated[str | None, Query(max_length=512)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> ConfigPage:
    page = services.list_suites(ctx, cursor=cursor, limit=limit)
    return ConfigPage(
        items=[ConfigOut.from_record(record) for record in page.items],
        next_cursor=page.next_cursor,
    )


@router.post("", response_model=ConfigOut, status_code=status.HTTP_201_CREATED)
def create_suite(
    payload: ConfigCreate,
    ctx: Annotated[TenantContext, Depends(get_tenant_context)],
    services: Annotated[SuitesPort, Depends(get_suites)],
    _: Annotated[Principal, Depends(require_scope("evaluators:write"))],
) -> ConfigOut:
    record = services.create_suite(
        ctx,
        name=payload.name,
        description=payload.description,
        config=payload.config,
    )
    return ConfigOut.from_record(record)


@router.get("/{suite_id}", response_model=ConfigOut)
def get_suite(
    suite_id: str,
    ctx: Annotated[TenantContext, Depends(get_tenant_context)],
    services: Annotated[SuitesPort, Depends(get_suites)],
    _: Annotated[Principal, Depends(require_scope("evaluators:read"))],
) -> ConfigOut:
    return ConfigOut.from_record(services.get_suite(ctx, suite_id))


__all__ = ["router"]
