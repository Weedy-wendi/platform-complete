"""Run creation, status, items, comparison and cancellation."""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, Query, status

from app.api.deps import get_evaluation, get_tenant_context, require_scope
from app.api.ports import EvaluationPort, RunItemStatus, RunSpec
from app.api.schemas import (
    CompareOut,
    RunAccepted,
    RunCancelOut,
    RunCreate,
    RunItemOut,
    RunItemPage,
    RunOut,
    RunPage,
)
from app.core.context import Principal, TenantContext

router = APIRouter(prefix="/runs", tags=["runs"])


@router.post("", response_model=RunAccepted, status_code=status.HTTP_202_ACCEPTED)
def create_run(
    payload: RunCreate,
    ctx: Annotated[TenantContext, Depends(get_tenant_context)],
    services: Annotated[EvaluationPort, Depends(get_evaluation)],
    _: Annotated[Principal, Depends(require_scope("runs:write"))],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key", max_length=128)] = None,
) -> RunAccepted:
    record = services.create_run(
        ctx,
        RunSpec(
            suite_id=payload.suite_id,
            suite_version=payload.suite_version,
            dataset_id=payload.dataset_id,
            dataset_version=payload.dataset_version,
            target_config=payload.target_config,
            baseline_run_id=payload.baseline_run_id,
        ),
        idempotency_key=idempotency_key,
    )
    return RunAccepted(run_id=record.run_id, status=record.status, manifest_hash=record.manifest_hash)


@router.get("", response_model=RunPage)
def list_runs(
    ctx: Annotated[TenantContext, Depends(get_tenant_context)],
    services: Annotated[EvaluationPort, Depends(get_evaluation)],
    _: Annotated[Principal, Depends(require_scope("runs:read"))],
    suite_id: Annotated[str | None, Query()] = None,
    cursor: Annotated[str | None, Query(max_length=512)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> RunPage:
    page = services.list_runs(ctx, suite_id=suite_id, cursor=cursor, limit=limit)
    return RunPage(items=[RunOut.from_record(record) for record in page.items], next_cursor=page.next_cursor)


@router.get("/{run_id}", response_model=RunOut)
def get_run(
    run_id: str,
    ctx: Annotated[TenantContext, Depends(get_tenant_context)],
    services: Annotated[EvaluationPort, Depends(get_evaluation)],
    _: Annotated[Principal, Depends(require_scope("runs:read"))],
) -> RunOut:
    return RunOut.from_record(services.get_run(ctx, run_id))


@router.get("/{run_id}/items", response_model=RunItemPage)
def list_run_items(
    run_id: str,
    ctx: Annotated[TenantContext, Depends(get_tenant_context)],
    services: Annotated[EvaluationPort, Depends(get_evaluation)],
    _: Annotated[Principal, Depends(require_scope("runs:read"))],
    item_status: Annotated[
        Literal["succeeded", "failed", "skipped", "error"] | None,
        Query(alias="status"),
    ] = None,
    cursor: Annotated[str | None, Query(max_length=512)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> RunItemPage:
    typed_status: RunItemStatus | None = item_status
    page = services.list_items(ctx, run_id, status=typed_status, cursor=cursor, limit=limit)
    return RunItemPage(
        items=[RunItemOut.from_record(record) for record in page.items],
        next_cursor=page.next_cursor,
    )


@router.post("/{run_id}/cancel", response_model=RunCancelOut, status_code=status.HTTP_202_ACCEPTED)
def cancel_run(
    run_id: str,
    ctx: Annotated[TenantContext, Depends(get_tenant_context)],
    services: Annotated[EvaluationPort, Depends(get_evaluation)],
    _: Annotated[Principal, Depends(require_scope("runs:write"))],
) -> RunCancelOut:
    record = services.cancel_run(ctx, run_id)
    return RunCancelOut(run_id=record.run_id, status=record.status)


@router.get("/{run_id}/compare", response_model=CompareOut)
def compare_run(
    run_id: str,
    ctx: Annotated[TenantContext, Depends(get_tenant_context)],
    services: Annotated[EvaluationPort, Depends(get_evaluation)],
    _: Annotated[Principal, Depends(require_scope("runs:read"))],
    baseline_run_id: Annotated[str, Query(min_length=1)],
) -> CompareOut:
    comparison = services.compare_runs(ctx, run_id, baseline_run_id)
    return CompareOut.from_record(comparison)


__all__ = ["router"]
