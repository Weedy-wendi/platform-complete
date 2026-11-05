"""Evaluator listing and configuration."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import get_evaluation, get_tenant_context, require_scope
from app.api.ports import EvaluationPort, EvaluatorSpec
from app.api.schemas import EvaluatorCreate, EvaluatorOut, EvaluatorPage
from app.core.context import Principal, TenantContext

router = APIRouter(prefix="/evaluators", tags=["evaluators"])


@router.get("", response_model=EvaluatorPage)
def list_evaluators(
    ctx: Annotated[TenantContext, Depends(get_tenant_context)],
    services: Annotated[EvaluationPort, Depends(get_evaluation)],
    _: Annotated[Principal, Depends(require_scope("evaluators:read"))],
    project_id: Annotated[str | None, Query()] = None,
) -> EvaluatorPage:
    records = services.list_evaluators(ctx, project_id=project_id)
    return EvaluatorPage(items=[EvaluatorOut.from_record(record) for record in records])


@router.post("", response_model=EvaluatorOut, status_code=status.HTTP_201_CREATED)
def create_evaluator(
    payload: EvaluatorCreate,
    ctx: Annotated[TenantContext, Depends(get_tenant_context)],
    services: Annotated[EvaluationPort, Depends(get_evaluation)],
    _: Annotated[Principal, Depends(require_scope("evaluators:write"))],
) -> EvaluatorOut:
    record = services.create_evaluator(
        ctx,
        EvaluatorSpec(
            name=payload.name,
            version=payload.version or "1",
            kind=payload.kind,
            project_id=payload.project_id,
            description=payload.description,
            metrics=tuple(metric.model_dump() for metric in payload.metrics),
            config=payload.config,
        ),
    )
    return EvaluatorOut.from_record(record)


@router.get("/{evaluator_id}", response_model=EvaluatorOut)
def get_evaluator(
    evaluator_id: str,
    ctx: Annotated[TenantContext, Depends(get_tenant_context)],
    services: Annotated[EvaluationPort, Depends(get_evaluation)],
    _: Annotated[Principal, Depends(require_scope("evaluators:read"))],
) -> EvaluatorOut:
    return EvaluatorOut.from_record(services.get_evaluator(ctx, evaluator_id))


__all__ = ["router"]
