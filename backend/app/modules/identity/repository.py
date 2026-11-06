"""Identity repositories.

Every tenant-owned query is filtered by ``tenant_id``. The base class from
``app.core.repository`` makes the filter the default; the extra lookups below
only add predicates on top of it.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.repository import TenantScopedRepository
from app.modules.identity.models import (
    Permission,
    Role,
    RolePermission,
    Tenant,
    User,
    UserRole,
)


class TenantRepository:
    """Tenant rows are global; they do not carry a parent ``tenant_id``."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, tenant_id: str) -> Tenant | None:
        tenant = self.session.get(Tenant, tenant_id)
        return tenant if tenant is not None and tenant.deleted_at is None else None

    def get_by_slug(self, slug: str) -> Tenant | None:
        return self.session.scalar(select(Tenant).where(Tenant.slug == slug, Tenant.deleted_at.is_(None)))

    def slug_exists(self, slug: str) -> bool:
        """Uniqueness includes soft-deleted rows to avoid a database error."""
        return self.session.scalar(select(Tenant.id).where(Tenant.slug == slug)) is not None

    def add(self, tenant: Tenant) -> Tenant:
        self.session.add(tenant)
        self.session.flush()
        return tenant


class UserRepository(TenantScopedRepository):
    def get_by_email(self, email: str) -> User | None:
        statement = self.scoped(User).where(User.email == email, User.deleted_at.is_(None))
        return self.session.scalar(statement)

    def email_exists(self, email: str) -> bool:
        """Uniqueness includes soft-deleted users to avoid a database error."""
        return self.session.scalar(self.scoped(User).where(User.email == email)) is not None

    def list_active(self) -> list[User]:
        statement = self.scoped(User).where(User.deleted_at.is_(None)).order_by(User.created_at)
        return list(self.session.scalars(statement))


class RoleRepository(TenantScopedRepository):
    def get_by_name(self, name: str) -> Role | None:
        statement = self.scoped(Role).where(Role.name == name, Role.deleted_at.is_(None))
        return self.session.scalar(statement)

    def name_exists(self, name: str) -> bool:
        """Uniqueness includes soft-deleted roles to avoid a database error."""
        return self.session.scalar(self.scoped(Role).where(Role.name == name)) is not None

    def list_active(self) -> list[Role]:
        statement = self.scoped(Role).where(Role.deleted_at.is_(None)).order_by(Role.name)
        return list(self.session.scalars(statement))


class PermissionRepository(TenantScopedRepository):
    def get_by_code(self, code: str) -> Permission | None:
        statement = self.scoped(Permission).where(Permission.code == code, Permission.deleted_at.is_(None))
        return self.session.scalar(statement)

    def get_by_code_including_deleted(self, code: str) -> Permission | None:
        return self.session.scalar(self.scoped(Permission).where(Permission.code == code))


class UserRoleRepository:
    def __init__(self, session: Session, tenant_id: str) -> None:
        self.session = session
        self.tenant_id = tenant_id

    def assign(self, user_id: str, role_id: str, *, created_by: str = "system") -> None:
        existing = self.session.get(UserRole, (self.tenant_id, user_id, role_id))
        if existing is None:
            self.session.add(
                UserRole(
                    tenant_id=self.tenant_id,
                    user_id=user_id,
                    role_id=role_id,
                    created_by=created_by,
                )
            )

    def remove(self, user_id: str, role_id: str) -> None:
        existing = self.session.get(UserRole, (self.tenant_id, user_id, role_id))
        if existing is not None:
            self.session.delete(existing)

    def role_ids_for_user(self, user_id: str) -> list[str]:
        statement = (
            select(UserRole.role_id)
            .where(UserRole.tenant_id == self.tenant_id, UserRole.user_id == user_id)
            .order_by(UserRole.role_id)
        )
        return list(self.session.scalars(statement))

    def role_names_for_user(self, user_id: str) -> list[str]:
        statement = (
            select(Role.name)
            .join(UserRole, (UserRole.role_id == Role.id) & (UserRole.tenant_id == Role.tenant_id))
            .where(
                UserRole.tenant_id == self.tenant_id,
                UserRole.user_id == user_id,
                Role.deleted_at.is_(None),
            )
            .order_by(Role.name)
        )
        return list(self.session.scalars(statement))


class RolePermissionRepository:
    def __init__(self, session: Session, tenant_id: str) -> None:
        self.session = session
        self.tenant_id = tenant_id

    def replace(self, role_id: str, permission_ids: list[str], *, created_by: str = "system") -> None:
        existing = list(
            self.session.scalars(
                select(RolePermission).where(
                    RolePermission.tenant_id == self.tenant_id,
                    RolePermission.role_id == role_id,
                )
            )
        )
        for link in existing:
            self.session.delete(link)
        for permission_id in permission_ids:
            self.session.add(
                RolePermission(
                    tenant_id=self.tenant_id,
                    role_id=role_id,
                    permission_id=permission_id,
                    created_by=created_by,
                )
            )

    def permission_codes_for_roles(self, role_names: list[str]) -> list[str]:
        if not role_names:
            return []
        statement = (
            select(Permission.code)
            .join(
                RolePermission,
                (RolePermission.permission_id == Permission.id) & (RolePermission.tenant_id == Permission.tenant_id),
            )
            .join(Role, (Role.id == RolePermission.role_id) & (Role.tenant_id == RolePermission.tenant_id))
            .where(
                RolePermission.tenant_id == self.tenant_id,
                Role.name.in_(role_names),
                Role.deleted_at.is_(None),
                Permission.deleted_at.is_(None),
            )
            .distinct()
            .order_by(Permission.code)
        )
        return list(self.session.scalars(statement))

    def permission_ids_for_role(self, role_id: str) -> list[str]:
        statement = select(RolePermission.permission_id).where(
            RolePermission.tenant_id == self.tenant_id,
            RolePermission.role_id == role_id,
        )
        return list(self.session.scalars(statement))
