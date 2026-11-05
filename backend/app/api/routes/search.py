"""Badcase search (delegated to the search module)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import get_search, get_tenant_context, require_scope
from app.api.ports import SearchPort
from app.api.schemas import BadcaseSearchIn, BadcaseSearchOut
from app.core.context import Principal, TenantContext

router = APIRouter(prefix="/badcases", tags=["badcases"])


@router.post("/search", response_model=BadcaseSearchOut)
def search_badcases(
    payload: BadcaseSearchIn,
    ctx: Annotated[TenantContext, Depends(get_tenant_context)],
    services: Annotated[SearchPort, Depends(get_search)],
    _: Annotated[Principal, Depends(require_scope("badcases:read"))],
) -> BadcaseSearchOut:
    result = services.search_badcases(
        ctx,
        query=payload.query,
        dataset_id=payload.dataset_id,
        tags=tuple(payload.tags),
        limit=payload.limit,
    )
    return BadcaseSearchOut.from_record(result)


__all__ = ["router"]
