"""Identity service tests (IDN-01/02/03/06)."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.core.clock import utcnow_naive
from app.core.context import TenantContext
from app.core.errors import ForbiddenError, InvalidArgumentError, NotFoundError, UnauthorizedError
from app.modules.identity.api_key import ApiKeyService
from app.modules.identity.models import Role, Tenant, User
from app.modules.identity.policies import IDENTITY_PERMISSIONS
from app.modules.identity.service import IdentityService
from app.modules.identity.views import TenantView


def test_create_tenant_and_reject_duplicate_slug(service: IdentityService, platform_ctx: TenantContext) -> None:
    tenant = service.create_tenant(platform_ctx, "Globex", "globex")
    assert tenant.slug == "globex"
    assert tenant.status == "active"
    with pytest.raises(InvalidArgumentError):
        service.create_tenant(platform_ctx, "Globex 2", "globex")


def test_create_user_with_multiple_roles(service: IdentityService, ctx: TenantContext) -> None:
    service.create_role(ctx, "viewer", {"identity:user:read"})
    service.create_role(ctx, "auditor", {"identity:audit:read"})
    user = service.create_user(ctx, "Alice@Example.com", roles=["viewer", "auditor"])

    assert user.email == "alice@example.com"
    assert user.roles == ("auditor", "viewer")
    assert service.permissions_for_user(ctx, user.id) == frozenset({"identity:user:read", "identity:audit:read"})
    assert service.can(ctx, user.id, "identity:user:read") is True
    assert service.can(ctx, user.id, "identity:user:create") is False


def test_unknown_role_is_rejected(service: IdentityService, ctx: TenantContext) -> None:
    with pytest.raises(InvalidArgumentError):
        service.create_user(ctx, "bob@example.com", roles=["missing"])


def test_service_enforces_permissions(service: IdentityService, tenant: TenantView) -> None:
    read_only = TenantContext(
        tenant_id=tenant.id,
        subject_id="viewer",
        scopes=frozenset({"identity:user:read"}),
        trace_id="trace-read",
    )
    with pytest.raises(ForbiddenError):
        service.create_user(read_only, "eve@example.com")
    with pytest.raises(ForbiddenError):
        service.create_role(read_only, "admin", {"identity:user:create"})


def test_cross_tenant_read_and_write_are_not_visible(service: IdentityService, ctx: TenantContext) -> None:
    user = service.create_user(ctx, "alice@example.com")
    service.create_role(ctx, "viewer", {"identity:user:read"})

    other = TenantContext(
        tenant_id="tenant-b",
        subject_id="admin-b",
        scopes=frozenset(IDENTITY_PERMISSIONS),
        trace_id="trace-b",
    )
    with pytest.raises(NotFoundError):
        service.get_user(other, user.id)
    with pytest.raises(NotFoundError):
        service.assign_role(other, user.id, "viewer")
    with pytest.raises(NotFoundError):
        service.deactivate_user(other, user.id)
    with pytest.raises(NotFoundError):
        service.list_users(other)


def test_soft_delete_hides_user(service: IdentityService, ctx: TenantContext) -> None:
    user = service.create_user(ctx, "gone@example.com")
    service.deactivate_user(ctx, user.id)
    with pytest.raises(NotFoundError):
        service.get_user(ctx, user.id)
    assert service.list_users(ctx) == []


def test_assign_and_remove_role(service: IdentityService, ctx: TenantContext) -> None:
    user = service.create_user(ctx, "carol@example.com")
    service.create_role(ctx, "viewer", {"identity:user:read"})
    service.assign_role(ctx, user.id, "viewer")
    assert service.get_user(ctx, user.id).roles == ("viewer",)
    assert service.permissions_for_user(ctx, user.id) == frozenset({"identity:user:read"})

    service.remove_role(ctx, user.id, "viewer")
    assert service.get_user(ctx, user.id).roles == ()


def test_unknown_permission_is_rejected(service: IdentityService, ctx: TenantContext) -> None:
    with pytest.raises(InvalidArgumentError):
        service.create_role(ctx, "bad", {"identity:unknown"})


def test_issue_revoke_and_rotate_api_key(
    service: IdentityService,
    api_key_service: ApiKeyService,
    ctx: TenantContext,
) -> None:
    issued = service.issue_api_key(ctx, name="ci", scopes={"mcp:projects:read"})
    assert api_key_service.verify(issued.raw_key).tenant_id == ctx.tenant_id

    replacement = service.rotate_api_key(ctx, issued.key_id)
    assert replacement.key_id != issued.key_id
    assert api_key_service.verify(replacement.raw_key).tenant_id == ctx.tenant_id
    with pytest.raises(UnauthorizedError):
        api_key_service.verify(issued.raw_key)

    service.revoke_api_key(ctx, replacement.key_id)
    with pytest.raises(UnauthorizedError):
        api_key_service.verify(replacement.raw_key)


def test_cross_tenant_key_revoke_is_not_visible(
    service: IdentityService,
    api_key_service: ApiKeyService,
    ctx: TenantContext,
) -> None:
    issued = service.issue_api_key(ctx, name="ci", scopes={"mcp:projects:read"})
    other = TenantContext(
        tenant_id="tenant-b",
        subject_id="admin-b",
        scopes=frozenset(IDENTITY_PERMISSIONS),
        trace_id="trace-b",
    )
    with pytest.raises(NotFoundError):
        service.revoke_api_key(other, issued.key_id)
    with pytest.raises(NotFoundError):
        service.rotate_api_key(other, issued.key_id)
    # The original key still works.
    assert api_key_service.verify(issued.raw_key).tenant_id == ctx.tenant_id


def test_identity_audit_events_contain_actor_target_and_trace(
    service: IdentityService,
    ctx: TenantContext,
    audit_writer,
) -> None:
    audit_writer.events.clear()
    user = service.create_user(ctx, "audit@example.com")
    service.create_role(ctx, "viewer", {"identity:user:read"})
    service.assign_role(ctx, user.id, "viewer")
    issued = service.issue_api_key(ctx, name="audit-key", scopes={"mcp:projects:read"})
    service.revoke_api_key(ctx, issued.key_id)
    service.record_login(ctx, user.id)

    actions = [event.action for event in audit_writer.events]
    assert "identity.user.created" in actions
    assert "identity.role.created" in actions
    assert "identity.role.changed" in actions
    assert "identity.key.issued" in actions
    assert "identity.key.revoked" in actions
    assert "identity.login" in actions

    for event in audit_writer.events:
        assert event.actor_id == ctx.subject_id
        assert event.trace_id == ctx.trace_id
        assert event.resource_id


def test_soft_deleted_user_email_cannot_be_reused(
    service: IdentityService,
    ctx: TenantContext,
    session_factory,
) -> None:
    user = service.create_user(ctx, "reuse@example.com")
    with session_factory() as session:
        row = session.scalar(select(User).where(User.id == user.id))
        assert row is not None
        row.deleted_at = utcnow_naive()
        session.commit()

    with pytest.raises(InvalidArgumentError):
        service.create_user(ctx, "reuse@example.com")


def test_soft_deleted_tenant_slug_cannot_be_reused(
    service: IdentityService,
    platform_ctx: TenantContext,
    session_factory,
) -> None:
    tenant = service.create_tenant(platform_ctx, "Old Co", "old-co")
    with session_factory() as session:
        row = session.get(Tenant, tenant.id)
        assert row is not None
        row.deleted_at = utcnow_naive()
        session.commit()

    with pytest.raises(InvalidArgumentError):
        service.create_tenant(platform_ctx, "Old Co 2", "old-co")


def test_soft_deleted_role_name_cannot_be_reused(
    service: IdentityService,
    ctx: TenantContext,
    session_factory,
) -> None:
    role = service.create_role(ctx, "legacy", {"identity:user:read"})
    with session_factory() as session:
        row = session.scalar(select(Role).where(Role.id == role.id))
        assert row is not None
        row.deleted_at = utcnow_naive()
        session.commit()

    with pytest.raises(InvalidArgumentError):
        service.create_role(ctx, "legacy", {"identity:user:read"})


def test_soft_deleted_tenant_blocks_auth_and_management(
    service: IdentityService,
    api_key_service: ApiKeyService,
    ctx: TenantContext,
    session_factory,
) -> None:
    issued = service.issue_api_key(ctx, name="deleted-tenant", scopes={"mcp:projects:read"})
    with session_factory() as session:
        tenant = session.get(Tenant, ctx.tenant_id)
        assert tenant is not None
        tenant.deleted_at = utcnow_naive()
        session.commit()

    api_key_service.invalidate_tenant_status(ctx.tenant_id)
    with pytest.raises(UnauthorizedError):
        api_key_service.verify(issued.raw_key)
    with pytest.raises(NotFoundError):
        service.create_user(ctx, "deleted@example.com")
    with pytest.raises(NotFoundError):
        service.list_users(ctx)


def test_disabled_tenant_blocks_auth_and_management(
    service: IdentityService,
    api_key_service: ApiKeyService,
    ctx: TenantContext,
) -> None:
    issued = service.issue_api_key(ctx, name="tenant-status", scopes={"mcp:projects:read"})
    assert api_key_service.verify(issued.raw_key).tenant_id == ctx.tenant_id

    service.set_tenant_status(ctx, ctx.tenant_id, "disabled")

    with pytest.raises(UnauthorizedError):
        api_key_service.verify(issued.raw_key)
    with pytest.raises(NotFoundError):
        service.create_user(ctx, "blocked@example.com")
    with pytest.raises(NotFoundError):
        service.list_users(ctx)
    with pytest.raises(NotFoundError):
        service.issue_api_key(ctx, name="blocked", scopes={"mcp:projects:read"})

    service.set_tenant_status(ctx, ctx.tenant_id, "active")
    assert api_key_service.verify(issued.raw_key).tenant_id == ctx.tenant_id
    assert service.create_user(ctx, "allowed@example.com").email == "allowed@example.com"
