"""Public report share-link resolution (017-rest-api FR-009/API-14)."""

from __future__ import annotations

import json
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from starlette.responses import JSONResponse, Response

from app.api.deps import get_reports, get_tenant_context
from app.api.ports import ReportsPort
from app.core.context import TenantContext

router = APIRouter(prefix="/share", tags=["reports"])


@router.get("/{token}")
def read_report_share(
    token: str,
    request: Request,
    ctx: Annotated[TenantContext, Depends(get_tenant_context)],
    services: Annotated[ReportsPort, Depends(get_reports)],
) -> Response:
    report = services.resolve_share_link(ctx, token, secret=request.app.state.report_share_secret)
    try:
        payload = json.loads(report.content)
    except (TypeError, ValueError):
        payload = {"run_id": report.run_id, "format": report.format, "content": report.content}
    return JSONResponse(payload)


__all__ = ["router"]
