"""Platform administration: tenants, users, roles, keys and providers."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.api.deps import get_admin, get_tenant_context, require_permission
from app.api.ports import AdminPort
from app.api.schemas import (
    ApiKeyCreate,
    IssuedKeyOut,
    ProviderOut,
    ProviderPage,
    RoleCreate,
    RoleOut,
    RolePage,
    TenantCreate,
    TenantOut,
    TenantPage,
    TenantStatusIn,
    UserCreate,
    UserOut,
    UserPage,
)
from app.core.context import Principal, TenantContext

router = APIRouter(prefix="/admin", tags=["admin"])


# Tenants -------------------------------------------------------------------


@router.get("/tenants", response_model=TenantPage)
def list_tenants(
    ctx: Annotated[TenantContext, Depends(get_tenant_context)],
    services: Annotated[AdminPort, Depends(get_admin)],
    _: Annotated[Principal, Depends(require_permission("identity:tenant:read"))],
) -> TenantPage:
    return TenantPage(items=[TenantOut.from_record(record) for record in services.list_tenants(ctx)])


@router.post("/tenants", response_model=TenantOut, status_code=status.HTTP_201_CREATED)
def create_tenant(
    payload: TenantCreate,
    ctx: Annotated[TenantContext, Depends(get_tenant_context)],
    services: Annotated[AdminPort, Depends(get_admin)],
    _: Annotated[Principal, Depends(require_permission("identity:tenant:create"))],
) -> TenantOut:
    return TenantOut.from_record(services.create_tenant(ctx, name=payload.name, slug=payload.slug))


@router.get("/tenants/{tenant_id}", response_model=TenantOut)
def get_tenant(
    tenant_id: str,
    ctx: Annotated[TenantContext, Depends(get_tenant_context)],
    services: Annotated[AdminPort, Depends(get_admin)],
    _: Annotated[Principal, Depends(require_permission("identity:tenant:read"))],
) -> TenantOut:
    return TenantOut.from_record(services.get_tenant(ctx, tenant_id))


@router.put("/tenants/{tenant_id}/status", response_model=TenantOut)
def set_tenant_status(
    tenant_id: str,
    payload: TenantStatusIn,
    ctx: Annotated[TenantContext, Depends(get_tenant_context)],
    services: Annotated[AdminPort, Depends(get_admin)],
    _: Annotated[Principal, Depends(require_permission("identity:tenant:write"))],
) -> TenantOut:
    return TenantOut.from_record(services.set_tenant_status(ctx, tenant_id, payload.status))


# Users ---------------------------------------------------------------------


@router.get("/users", response_model=UserPage)
def list_users(
    ctx: Annotated[TenantContext, Depends(get_tenant_context)],
    services: Annotated[AdminPort, Depends(get_admin)],
    _: Annotated[Principal, Depends(require_permission("identity:user:read"))],
) -> UserPage:
    return UserPage(items=[UserOut.from_record(record) for record in services.list_users(ctx)])


@router.post("/users", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_user(
    payload: UserCreate,
    ctx: Annotated[TenantContext, Depends(get_tenant_context)],
    services: Annotated[AdminPort, Depends(get_admin)],
    _: Annotated[Principal, Depends(require_permission("identity:user:create"))],
) -> UserOut:
    return UserOut.from_record(services.create_user(ctx, email=payload.email, roles=tuple(payload.roles)))


@router.get("/users/{user_id}", response_model=UserOut)
def get_user(
    user_id: str,
    ctx: Annotated[TenantContext, Depends(get_tenant_context)],
    services: Annotated[AdminPort, Depends(get_admin)],
    _: Annotated[Principal, Depends(require_permission("identity:user:read"))],
) -> UserOut:
    return UserOut.from_record(services.get_user(ctx, user_id))


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def deactivate_user(
    user_id: str,
    ctx: Annotated[TenantContext, Depends(get_tenant_context)],
    services: Annotated[AdminPort, Depends(get_admin)],
    _: Annotated[Principal, Depends(require_permission("identity:user:deactivate"))],
) -> None:
    services.deactivate_user(ctx, user_id)


# Roles ---------------------------------------------------------------------


@router.get("/roles", response_model=RolePage)
def list_roles(
    ctx: Annotated[TenantContext, Depends(get_tenant_context)],
    services: Annotated[AdminPort, Depends(get_admin)],
    _: Annotated[Principal, Depends(require_permission("identity:role:write"))],
) -> RolePage:
    return RolePage(items=[RoleOut.from_record(record) for record in services.list_roles(ctx)])


@router.post("/roles", response_model=RoleOut, status_code=status.HTTP_201_CREATED)
def create_role(
    payload: RoleCreate,
    ctx: Annotated[TenantContext, Depends(get_tenant_context)],
    services: Annotated[AdminPort, Depends(get_admin)],
    _: Annotated[Principal, Depends(require_permission("identity:role:write"))],
) -> RoleOut:
    return RoleOut.from_record(
        services.create_role(
            ctx,
            name=payload.name,
            permissions=tuple(payload.permissions),
            description=payload.description,
        )
    )


# API keys ------------------------------------------------------------------


@router.post("/api-keys", response_model=IssuedKeyOut, status_code=status.HTTP_201_CREATED)
def issue_api_key(
    payload: ApiKeyCreate,
    ctx: Annotated[TenantContext, Depends(get_tenant_context)],
    services: Annotated[AdminPort, Depends(get_admin)],
    _: Annotated[Principal, Depends(require_permission("identity:api_key:issue"))],
) -> IssuedKeyOut:
    return IssuedKeyOut.from_record(
        services.issue_api_key(
            ctx,
            name=payload.name,
            scopes=tuple(payload.scopes),
            expires_at=payload.expires_at,
        )
    )


@router.delete("/api-keys/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_api_key(
    key_id: str,
    ctx: Annotated[TenantContext, Depends(get_tenant_context)],
    services: Annotated[AdminPort, Depends(get_admin)],
    _: Annotated[Principal, Depends(require_permission("identity:api_key:revoke"))],
) -> None:
    services.revoke_api_key(ctx, key_id)


@router.post("/api-keys/{key_id}/rotate", response_model=IssuedKeyOut, status_code=status.HTTP_201_CREATED)
def rotate_api_key(
    key_id: str,
    ctx: Annotated[TenantContext, Depends(get_tenant_context)],
    services: Annotated[AdminPort, Depends(get_admin)],
    _: Annotated[Principal, Depends(require_permission("identity:api_key:rotate"))],
) -> IssuedKeyOut:
    return IssuedKeyOut.from_record(services.rotate_api_key(ctx, key_id))


# Providers -----------------------------------------------------------------


@router.get("/providers", response_model=ProviderPage)
def list_providers(
    ctx: Annotated[TenantContext, Depends(get_tenant_context)],
    services: Annotated[AdminPort, Depends(get_admin)],
    _: Annotated[Principal, Depends(require_permission("admin:read"))],
) -> ProviderPage:
    return ProviderPage(items=[ProviderOut.from_record(record) for record in services.list_providers(ctx)])


__all__ = ["router"]
