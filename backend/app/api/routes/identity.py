"""Current principal endpoint."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import get_principal
from app.api.schemas import MeOut
from app.core.context import Principal

router = APIRouter(prefix="/identity", tags=["identity"])


@router.get("/me", response_model=MeOut)
def get_me(principal: Annotated[Principal, Depends(get_principal)]) -> MeOut:
    return MeOut(
        tenant_id=principal.tenant_id,
        subject_id=principal.subject_id,
        scopes=sorted(principal.scopes),
        auth_method=principal.auth_method,
        expires_at=principal.expires_at,
        client_id=principal.client_id,
        api_key_id=principal.api_key_id,
    )


__all__ = ["router"]
