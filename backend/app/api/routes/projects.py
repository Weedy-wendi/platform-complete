"""Project CRUD."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, status

from app.api.deps import get_projects, get_tenant_context, require_scope
from app.api.ports import ProjectsPort
from app.api.schemas import ProjectCreate, ProjectOut, ProjectPage, ProjectUpdate
from app.core.context import Principal, TenantContext

router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("", response_model=ProjectPage)
def list_projects(
    ctx: Annotated[TenantContext, Depends(get_tenant_context)],
    services: Annotated[ProjectsPort, Depends(get_projects)],
    _: Annotated[Principal, Depends(require_scope("projects:read"))],
    cursor: Annotated[str | None, Query(max_length=512)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> ProjectPage:
    page = services.list_projects(ctx, cursor=cursor, limit=limit)
    return ProjectPage(
        items=[ProjectOut.from_record(record) for record in page.items],
        next_cursor=page.next_cursor,
    )


@router.post("", response_model=ProjectOut, status_code=status.HTTP_201_CREATED)
def create_project(
    payload: ProjectCreate,
    ctx: Annotated[TenantContext, Depends(get_tenant_context)],
    services: Annotated[ProjectsPort, Depends(get_projects)],
    _: Annotated[Principal, Depends(require_scope("projects:write"))],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key", max_length=128)] = None,
) -> ProjectOut:
    record = services.create_project(
        ctx,
        name=payload.name,
        description=payload.description,
        idempotency_key=idempotency_key,
    )
    return ProjectOut.from_record(record)


@router.get("/{project_id}", response_model=ProjectOut)
def get_project(
    project_id: str,
    ctx: Annotated[TenantContext, Depends(get_tenant_context)],
    services: Annotated[ProjectsPort, Depends(get_projects)],
    _: Annotated[Principal, Depends(require_scope("projects:read"))],
) -> ProjectOut:
    return ProjectOut.from_record(services.get_project(ctx, project_id))


@router.patch("/{project_id}", response_model=ProjectOut)
def update_project(
    project_id: str,
    payload: ProjectUpdate,
    ctx: Annotated[TenantContext, Depends(get_tenant_context)],
    services: Annotated[ProjectsPort, Depends(get_projects)],
    _: Annotated[Principal, Depends(require_scope("projects:write"))],
) -> ProjectOut:
    record = services.update_project(
        ctx,
        project_id,
        name=payload.name,
        description=payload.description,
    )
    return ProjectOut.from_record(record)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(
    project_id: str,
    ctx: Annotated[TenantContext, Depends(get_tenant_context)],
    services: Annotated[ProjectsPort, Depends(get_projects)],
    _: Annotated[Principal, Depends(require_scope("projects:write"))],
) -> None:
    services.delete_project(ctx, project_id)


__all__ = ["router"]
