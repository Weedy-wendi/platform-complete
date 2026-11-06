"""RBAC and scope policy helpers.

Policies are pure: callers pass the roles or scopes they already resolved.
Anything not explicitly allowed is denied.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

from app.core.context import Principal, TenantContext
from app.core.errors import ForbiddenError

IDENTITY_PERMISSIONS: frozenset[str] = frozenset(
    {
        "identity:tenant:create",
        "identity:tenant:read",
        "identity:tenant:write",
        "identity:user:create",
        "identity:user:read",
        "identity:user:deactivate",
        "identity:role:write",
        "identity:role:assign",
        "identity:api_key:issue",
        "identity:api_key:revoke",
        "identity:api_key:rotate",
        "identity:audit:read",
    }
)

DEFAULT_ROLE_PERMISSIONS: Mapping[str, frozenset[str]] = {
    "tenant_admin": IDENTITY_PERMISSIONS,
    "identity_admin": frozenset(
        {
            "identity:user:create",
            "identity:user:read",
            "identity:user:deactivate",
            "identity:role:write",
            "identity:role:assign",
            "identity:api_key:issue",
            "identity:api_key:revoke",
            "identity:api_key:rotate",
        }
    ),
    "viewer": frozenset({"identity:user:read"}),
    "auditor": frozenset({"identity:audit:read"}),
}


@dataclass(frozen=True)
class AccessPolicy:
    role_permissions: Mapping[str, frozenset[str]] = field(default_factory=lambda: dict(DEFAULT_ROLE_PERMISSIONS))

    def permissions_for(self, roles: Iterable[str]) -> frozenset[str]:
        permissions: set[str] = set()
        for role in roles:
            permissions.update(self.role_permissions.get(role, frozenset()))
        return frozenset(permissions)

    def can(self, roles: Iterable[str], permission: str) -> bool:
        return permission in self.permissions_for(roles)

    def require(self, roles: Iterable[str], permission: str) -> None:
        if not self.can(roles, permission):
            raise ForbiddenError(required_permission=permission)


def require_permission(subject: TenantContext | Principal, permission: str) -> None:
    if permission not in subject.scopes:
        raise ForbiddenError(required_permission=permission)


def require_scope(subject: TenantContext | Principal, scope: str) -> None:
    if scope not in subject.scopes:
        raise ForbiddenError(required_scope=scope)


def require_any_scope(subject: TenantContext | Principal, scopes: Iterable[str]) -> None:
    required = frozenset(scopes)
    if not required.intersection(subject.scopes):
        raise ForbiddenError(required_scopes=sorted(required))
