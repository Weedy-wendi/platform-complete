"""Run report generation, export and signed share links."""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request
from starlette.responses import Response

from app.api.deps import get_reports, get_tenant_context, require_scope
from app.api.ports import ReportsPort
from app.api.schemas import ShareLinkCreate, ShareLinkOut
from app.core.context import Principal, TenantContext

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/{run_id}")
def get_report(
    run_id: str,
    ctx: Annotated[TenantContext, Depends(get_tenant_context)],
    services: Annotated[ReportsPort, Depends(get_reports)],
    _: Annotated[Principal, Depends(require_scope("reports:read"))],
    format: Annotated[Literal["json", "markdown", "csv", "junit"], Query()] = "json",
) -> Response:
    report = services.get_report(ctx, run_id, format)
    return Response(
        content=report.content,
        media_type=report.media_type,
        headers={"Content-Disposition": f'attachment; filename="{run_id}.{format}"'},
    )


@router.post("/{run_id}/share", response_model=ShareLinkOut)
def create_report_share(
    run_id: str,
    payload: ShareLinkCreate,
    request: Request,
    ctx: Annotated[TenantContext, Depends(get_tenant_context)],
    services: Annotated[ReportsPort, Depends(get_reports)],
    _: Annotated[Principal, Depends(require_scope("reports:read"))],
) -> ShareLinkOut:
    record = services.create_share_link(
        ctx,
        run_id,
        secret=request.app.state.report_share_secret,
        ttl_seconds=payload.ttl_seconds,
    )
    return ShareLinkOut.from_record(record)


__all__ = ["router"]
