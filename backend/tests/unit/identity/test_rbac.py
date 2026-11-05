"""RBAC policy tests (IDN-02)."""

from __future__ import annotations

import pytest

from app.core.errors import ForbiddenError
from app.modules.identity.policies import (
    IDENTITY_PERMISSIONS,
    AccessPolicy,
    require_any_scope,
    require_permission,
    require_scope,
)


def test_default_deny_for_unknown_roles() -> None:
    policy = AccessPolicy()
    assert policy.can([], "identity:user:read") is False
    assert policy.can(["missing"], "identity:user:read") is False


def test_roles_compose_permissions() -> None:
    policy = AccessPolicy()
    permissions = policy.permissions_for(["viewer", "auditor"])
    assert permissions == frozenset({"identity:user:read", "identity:audit:read"})


def test_require_raises_forbidden_with_permission_detail() -> None:
    policy = AccessPolicy({"viewer": frozenset({"identity:user:read"})})
    with pytest.raises(ForbiddenError) as excinfo:
        policy.require(["viewer"], "identity:user:create")
    assert excinfo.value.code == "FORBIDDEN"
    assert excinfo.value.details["required_permission"] == "identity:user:create"


def test_tenant_admin_has_all_identity_permissions() -> None:
    policy = AccessPolicy()
    assert policy.permissions_for(["tenant_admin"]) == IDENTITY_PERMISSIONS


def test_scope_helpers_default_deny() -> None:
    from app.core.context import Principal

    principal = Principal(tenant_id="tenant-a", subject="user:1", scopes=frozenset({"mcp:projects:read"}))
    require_scope(principal, "mcp:projects:read")
    require_any_scope(principal, {"mcp:eval:read", "mcp:projects:read"})
    with pytest.raises(ForbiddenError):
        require_scope(principal, "mcp:eval:read")
    with pytest.raises(ForbiddenError):
        require_any_scope(principal, {"mcp:eval:read", "mcp:gate:read"})
    with pytest.raises(ForbiddenError):
        require_permission(principal, "identity:user:create")
