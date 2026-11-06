"""Cross-tenant isolation for identity (IDN-05).

Covers read, write and list operations plus API-key tenant binding. Export and
download are not implemented in P0a, so their isolation cases are covered when
the reporting/assets modules arrive.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine

from app.core.context import TenantContext
from app.core.db import Base, make_session_factory
from app.core.errors import NotFoundError, UnauthorizedError
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

_TABLES = [
    Tenant.__table__,
    User.__table__,
    Role.__table__,
    Permission.__table__,
    UserRole.__table__,
    RolePermission.__table__,
]


@pytest.fixture()
def service():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine, tables=_TABLES)
    factory = make_session_factory(engine)
    api_keys = ApiKeyService(InMemoryApiKeyStore(), pepper="pepper")
    svc = IdentityService(factory, api_keys, InMemoryAuditLogWriter())
    platform = TenantContext(
        tenant_id="platform",
        subject_id="admin",
        scopes=frozenset(IDENTITY_PERMISSIONS),
        trace_id="trace-platform",
    )
    tenant_a = svc.create_tenant(platform, "Alpha", "alpha")
    tenant_b = svc.create_tenant(platform, "Beta", "beta")
    try:
        yield (
            svc,
            api_keys,
            TenantContext(
                tenant_id=tenant_a.id,
                subject_id="admin-a",
                scopes=frozenset(IDENTITY_PERMISSIONS),
                trace_id="trace-a",
            ),
            TenantContext(
                tenant_id=tenant_b.id,
                subject_id="admin-b",
                scopes=frozenset(IDENTITY_PERMISSIONS),
                trace_id="trace-b",
            ),
        )
    finally:
        engine.dispose()


def test_cross_tenant_read_is_404(service) -> None:
    svc, _, ctx_a, ctx_b = service
    user = svc.create_user(ctx_a, "alice@alpha.test")
    with pytest.raises(NotFoundError):
        svc.get_user(ctx_b, user.id)


def test_cross_tenant_list_excludes_other_tenant(service) -> None:
    svc, _, ctx_a, ctx_b = service
    svc.create_user(ctx_a, "alice@alpha.test")
    svc.create_user(ctx_b, "bob@beta.test")
    assert [user.email for user in svc.list_users(ctx_a)] == ["alice@alpha.test"]
    assert [user.email for user in svc.list_users(ctx_b)] == ["bob@beta.test"]


def test_cross_tenant_write_is_rejected(service) -> None:
    svc, _, ctx_a, ctx_b = service
    user = svc.create_user(ctx_a, "alice@alpha.test")
    svc.create_role(ctx_a, "viewer", {"identity:user:read"})
    with pytest.raises(NotFoundError):
        svc.assign_role(ctx_b, user.id, "viewer")
    with pytest.raises(NotFoundError):
        svc.deactivate_user(ctx_b, user.id)


def test_cross_tenant_api_key_is_not_visible(service) -> None:
    svc, api_keys, ctx_a, ctx_b = service
    issued = svc.issue_api_key(ctx_a, name="alpha", scopes={"mcp:projects:read"})
    assert api_keys.verify(issued.raw_key).tenant_id == ctx_a.tenant_id
    with pytest.raises(NotFoundError):
        svc.revoke_api_key(ctx_b, issued.key_id)
    with pytest.raises(NotFoundError):
        svc.rotate_api_key(ctx_b, issued.key_id)
    assert api_keys.verify(issued.raw_key).tenant_id == ctx_a.tenant_id


def test_revoked_key_is_rejected_even_from_cache(service) -> None:
    svc, api_keys, ctx_a, _ = service
    issued = svc.issue_api_key(ctx_a, name="alpha", scopes={"mcp:projects:read"})
    assert api_keys.verify(issued.raw_key).tenant_id == ctx_a.tenant_id
    svc.revoke_api_key(ctx_a, issued.key_id)
    with pytest.raises(UnauthorizedError):
        api_keys.verify(issued.raw_key)
