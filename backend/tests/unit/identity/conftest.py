"""Shared identity test fixtures."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine

from app.core.context import TenantContext
from app.core.db import Base, make_session_factory
from app.modules.audit.models import AuditLog
from app.modules.audit.writer import InMemoryAuditLogWriter
from app.modules.identity.api_key import ApiKeyService, InMemoryApiKeyStore
from app.modules.identity.models import (
    Permission,
    Role,
    RolePermission,
    Tenant,
    User,
    UserRole,
)
from app.modules.identity.policies import IDENTITY_PERMISSIONS
from app.modules.identity.service import IdentityService
from app.modules.identity.views import TenantView

_TABLES = [
    Tenant.__table__,
    User.__table__,
    Role.__table__,
    Permission.__table__,
    UserRole.__table__,
    RolePermission.__table__,
    AuditLog.__table__,
]


@pytest.fixture()
def session_factory():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine, tables=_TABLES)
    try:
        yield make_session_factory(engine)
    finally:
        engine.dispose()


@pytest.fixture()
def audit_writer() -> InMemoryAuditLogWriter:
    return InMemoryAuditLogWriter()


@pytest.fixture()
def api_key_service() -> ApiKeyService:
    return ApiKeyService(InMemoryApiKeyStore(), pepper="test-pepper", key_env="test")


@pytest.fixture()
def service(
    session_factory,
    api_key_service: ApiKeyService,
    audit_writer: InMemoryAuditLogWriter,
) -> IdentityService:
    return IdentityService(session_factory, api_key_service, audit_writer)


@pytest.fixture()
def platform_ctx() -> TenantContext:
    return TenantContext(
        tenant_id="platform",
        subject_id="admin",
        scopes=frozenset(IDENTITY_PERMISSIONS),
        trace_id="trace-platform",
    )


@pytest.fixture()
def tenant(service: IdentityService, platform_ctx: TenantContext) -> TenantView:
    return service.create_tenant(platform_ctx, "Acme", "acme")


@pytest.fixture()
def ctx(tenant: TenantView) -> TenantContext:
    return TenantContext(
        tenant_id=tenant.id,
        subject_id="admin",
        scopes=frozenset(IDENTITY_PERMISSIONS),
        trace_id="trace-1",
    )
