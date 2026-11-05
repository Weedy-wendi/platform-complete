"""Gate result queries (delegated to the gate module)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import get_gates, get_tenant_context, require_scope
from app.api.ports import GatePort
from app.api.schemas import GateOut
from app.core.context import Principal, TenantContext
from app.core.errors import NotFoundError

router = APIRouter(prefix="/gates", tags=["gates"])


@router.get("/{suite_id}/{run_id}", response_model=GateOut)
def get_gate(
    suite_id: str,
    run_id: str,
    ctx: Annotated[TenantContext, Depends(get_tenant_context)],
    services: Annotated[GatePort, Depends(get_gates)],
    _: Annotated[Principal, Depends(require_scope("gate:read"))],
) -> GateOut:
    result = services.read_gate(ctx, suite_id=suite_id, run_id=run_id)
    if result is None:
        raise NotFoundError("Gate result not found", suite_id=suite_id)
    return GateOut.from_record(result)


__all__ = ["router"]
