"""Identity service + SQL audit integration tests (opt-in testcontainers)."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.context import TenantContext
from app.core.db import Base, create_engine_from_dsn, make_session_factory
from app.modules.audit.models import AuditLog
from app.modules.audit.writer import SqlAuditLogWriter
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
    AuditLog.__table__,
]


def test_identity_flow_persists_users_roles_and_audit(mysql_dsn: str) -> None:
    engine = create_engine_from_dsn(mysql_dsn)
    Base.metadata.create_all(engine, tables=_TABLES)
    try:
        factory = make_session_factory(engine)
        service = IdentityService(
            factory,
            ApiKeyService(InMemoryApiKeyStore(), pepper="pepper"),
            SqlAuditLogWriter(factory),
        )
        platform = TenantContext(
            tenant_id="platform",
            subject_id="admin",
            scopes=frozenset(IDENTITY_PERMISSIONS),
            trace_id="trace-platform",
        )
        tenant = service.create_tenant(platform, "Acme", "acme")
        ctx = TenantContext(
            tenant_id=tenant.id,
            subject_id="admin",
            scopes=frozenset(IDENTITY_PERMISSIONS),
            trace_id="trace-1",
        )
        service.create_role(ctx, "viewer", {"identity:user:read"})
        user = service.create_user(ctx, "alice@example.com", roles=["viewer"])
        service.assign_role(ctx, user.id, "viewer")
        service.record_login(ctx, user.id)

        assert service.get_user(ctx, user.id).roles == ("viewer",)
        assert service.permissions_for_user(ctx, user.id) == frozenset({"identity:user:read"})

        with Session(engine) as session:
            assert session.scalar(select(func.count()).select_from(User)) == 1
            assert session.scalar(select(func.count()).select_from(Tenant)) == 1
            assert session.scalar(select(func.count()).select_from(AuditLog)) == 5
            actions = list(session.scalars(select(AuditLog.action).order_by(AuditLog.action)))
            assert "identity.login" in actions
            assert "identity.user.created" in actions
            assert "identity.role.changed" in actions
    finally:
        Base.metadata.drop_all(engine, tables=_TABLES)
        engine.dispose()
