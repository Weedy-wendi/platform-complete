"""Functional test runs (P2 adapter surface)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, status

from app.api.deps import get_functional, get_tenant_context, require_scope
from app.api.ports import FunctionalPort
from app.api.schemas import FunctionalRunCreate, FunctionalRunOut, FunctionalRunPage
from app.core.context import Principal, TenantContext

router = APIRouter(prefix="/functional", tags=["functional"])


@router.get("/runs", response_model=FunctionalRunPage)
def list_functional_runs(
    ctx: Annotated[TenantContext, Depends(get_tenant_context)],
    services: Annotated[FunctionalPort, Depends(get_functional)],
    _: Annotated[Principal, Depends(require_scope("functional:read"))],
    cursor: Annotated[str | None, Query(max_length=512)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> FunctionalRunPage:
    page = services.list_runs(ctx, cursor=cursor, limit=limit)
    return FunctionalRunPage(
        items=[FunctionalRunOut.from_record(record) for record in page.items],
        next_cursor=page.next_cursor,
    )


@router.post("/runs", response_model=FunctionalRunOut, status_code=status.HTTP_202_ACCEPTED)
def create_functional_run(
    payload: FunctionalRunCreate,
    ctx: Annotated[TenantContext, Depends(get_tenant_context)],
    services: Annotated[FunctionalPort, Depends(get_functional)],
    _: Annotated[Principal, Depends(require_scope("functional:write"))],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key", max_length=128)] = None,
) -> FunctionalRunOut:
    record = services.create_run(
        ctx,
        suite_id=payload.suite_id,
        suite_version=payload.suite_version,
        idempotency_key=idempotency_key,
    )
    return FunctionalRunOut.from_record(record)


@router.get("/runs/{run_id}", response_model=FunctionalRunOut)
def get_functional_run(
    run_id: str,
    ctx: Annotated[TenantContext, Depends(get_tenant_context)],
    services: Annotated[FunctionalPort, Depends(get_functional)],
    _: Annotated[Principal, Depends(require_scope("functional:read"))],
) -> FunctionalRunOut:
    return FunctionalRunOut.from_record(services.get_run(ctx, run_id))


__all__ = ["router"]
