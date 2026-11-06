"""Dataset search, creation and immutable version publishing."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, status

from app.api.deps import get_datasets, get_tenant_context, require_scope
from app.api.ports import DatasetsPort
from app.api.schemas import (
    DatasetCreate,
    DatasetOut,
    DatasetPage,
    DatasetVersionCreate,
    DatasetVersionOut,
    SampleOut,
    SamplePage,
)
from app.core.context import Principal, TenantContext

router = APIRouter(prefix="/datasets", tags=["datasets"])


@router.get("", response_model=DatasetPage)
def search_datasets(
    ctx: Annotated[TenantContext, Depends(get_tenant_context)],
    services: Annotated[DatasetsPort, Depends(get_datasets)],
    _: Annotated[Principal, Depends(require_scope("datasets:read"))],
    query: Annotated[str | None, Query(max_length=200)] = None,
    project_id: Annotated[str | None, Query()] = None,
    tags: Annotated[list[str] | None, Query()] = None,
    cursor: Annotated[str | None, Query(max_length=512)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> DatasetPage:
    page = services.search_datasets(
        ctx,
        query=query,
        project_id=project_id,
        tags=tuple(tags or ()),
        cursor=cursor,
        limit=limit,
    )
    return DatasetPage(
        items=[DatasetOut.from_record(record) for record in page.items],
        next_cursor=page.next_cursor,
    )


@router.post("", response_model=DatasetOut, status_code=status.HTTP_201_CREATED)
def create_dataset(
    payload: DatasetCreate,
    ctx: Annotated[TenantContext, Depends(get_tenant_context)],
    services: Annotated[DatasetsPort, Depends(get_datasets)],
    _: Annotated[Principal, Depends(require_scope("datasets:write"))],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key", max_length=128)] = None,
) -> DatasetOut:
    record = services.create_dataset(
        ctx,
        project_id=payload.project_id,
        name=payload.name,
        tags=tuple(payload.tags),
        idempotency_key=idempotency_key,
    )
    return DatasetOut.from_record(record)


@router.post(
    "/{dataset_id}/versions",
    response_model=DatasetVersionOut,
    status_code=status.HTTP_201_CREATED,
)
def publish_dataset_version(
    dataset_id: str,
    payload: DatasetVersionCreate,
    ctx: Annotated[TenantContext, Depends(get_tenant_context)],
    services: Annotated[DatasetsPort, Depends(get_datasets)],
    _: Annotated[Principal, Depends(require_scope("datasets:write"))],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key", max_length=128)] = None,
) -> DatasetVersionOut:
    record = services.publish_version(
        ctx,
        dataset_id,
        schema=payload.schema_,
        content_hash=payload.content_hash,
        samples=tuple(sample.model_dump() for sample in payload.samples),
        idempotency_key=idempotency_key,
    )
    return DatasetVersionOut.from_record(record)


@router.get("/{dataset_id}/versions/{version}/samples", response_model=SamplePage)
def page_dataset_samples(
    dataset_id: str,
    version: int,
    ctx: Annotated[TenantContext, Depends(get_tenant_context)],
    services: Annotated[DatasetsPort, Depends(get_datasets)],
    _: Annotated[Principal, Depends(require_scope("datasets:read"))],
    cursor: Annotated[str | None, Query(max_length=512)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> SamplePage:
    page = services.page_samples(ctx, dataset_id, version, cursor=cursor, limit=limit)
    return SamplePage(
        items=[SampleOut.from_record(record) for record in page.items],
        next_cursor=page.next_cursor,
    )


__all__ = ["router"]
