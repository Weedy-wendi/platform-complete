"""Identity use cases: tenants, users, roles and API keys.

The service is framework-agnostic. Each public method accepts a
``TenantContext``, enforces an explicit permission and writes an audit event
after the transaction commits.
"""

from __future__ import annotations

import re
from datetime import datetime

from sqlalchemy.orm import Session, sessionmaker

from app.core.clock import utcnow_naive
from app.core.context import TenantContext
from app.core.errors import InvalidArgumentError, NotFoundError
from app.core.ids import new_ulid
from app.core.logging import get_logger
from app.core.metrics import AUDIT_WRITE_FAILED
from app.modules.audit.public import AuditLogEvent, AuditLogWriter
from app.modules.identity.api_key import ApiKeyService, IssuedApiKey
from app.modules.identity.models import Permission, Role, Tenant, User
from app.modules.identity.policies import (
    IDENTITY_PERMISSIONS,
    AccessPolicy,
    require_permission,
)
from app.modules.identity.repository import (
    PermissionRepository,
    RolePermissionRepository,
    RoleRepository,
    TenantRepository,
    UserRepository,
    UserRoleRepository,
)
from app.modules.identity.tenant_status import SqlTenantStatusChecker
from app.modules.identity.views import RoleView, TenantView, UserView

logger = get_logger(__name__)

_SLUG_PATTERN = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$")


class IdentityService:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        api_key_service: ApiKeyService,
        audit_writer: AuditLogWriter | None = None,
        *,
        policy: AccessPolicy | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._api_keys = api_key_service
        self._audit_writer = audit_writer
        self._policy = policy or AccessPolicy()
        if api_key_service.tenant_status_checker is None:
            api_key_service.set_tenant_status_checker(SqlTenantStatusChecker(session_factory))

    def _require_active_tenant(self, tenant_id: str) -> None:
        with self._session_factory() as session:
            tenant = TenantRepository(session).get(tenant_id)
            if tenant is None or tenant.status != "active":
                raise NotFoundError("Tenant not found or disabled")

    # Tenants ---------------------------------------------------------------

    def create_tenant(self, ctx: TenantContext, name: str, slug: str) -> TenantView:
        require_permission(ctx, "identity:tenant:create")
        if not name.strip():
            raise InvalidArgumentError("tenant name is required")
        if not _SLUG_PATTERN.fullmatch(slug):
            raise InvalidArgumentError(
                "tenant slug must be 1-64 lowercase letters, digits or hyphens",
                slug=slug,
            )

        with self._session_factory() as session:
            tenants = TenantRepository(session)
            if tenants.slug_exists(slug):
                raise InvalidArgumentError("tenant slug already exists", slug=slug)
            tenant = Tenant(
                id=new_ulid(),
                name=name.strip(),
                slug=slug,
                status="active",
                created_by=ctx.subject_id,
                updated_by=ctx.subject_id,
            )
            tenants.add(tenant)
            session.commit()
            view = TenantView(id=tenant.id, name=tenant.name, slug=tenant.slug, status=tenant.status)

        self._audit(ctx, "identity.tenant.created", "tenant", view.id)
        return view

    def get_tenant(self, ctx: TenantContext, tenant_id: str) -> TenantView:
        require_permission(ctx, "identity:tenant:read")
        with self._session_factory() as session:
            tenant = TenantRepository(session).get(tenant_id)
            if tenant is None:
                raise NotFoundError("Tenant not found")
            return TenantView(id=tenant.id, name=tenant.name, slug=tenant.slug, status=tenant.status)

    def set_tenant_status(self, ctx: TenantContext, tenant_id: str, status: str) -> None:
        require_permission(ctx, "identity:tenant:write")
        if status not in {"active", "disabled"}:
            raise InvalidArgumentError("tenant status must be active or disabled", status=status)
        with self._session_factory() as session:
            tenant = TenantRepository(session).get(tenant_id)
            if tenant is None:
                raise NotFoundError("Tenant not found")
            tenant.status = status
            tenant.updated_by = ctx.subject_id
            session.commit()
        self._api_keys.invalidate_tenant_status(tenant_id)
        self._audit(
            ctx,
            "identity.tenant.status_changed",
            "tenant",
            tenant_id,
            detail={"status": status},
        )

    # Users -----------------------------------------------------------------

    def create_user(
        self,
        ctx: TenantContext,
        email: str,
        roles: list[str] | None = None,
    ) -> UserView:
        require_permission(ctx, "identity:user:create")
        self._require_active_tenant(ctx.tenant_id)
        normalized = email.strip().lower()
        if "@" not in normalized or normalized.startswith("@") or normalized.endswith("@"):
            raise InvalidArgumentError("valid email is required", email=email)

        with self._session_factory() as session:
            users = UserRepository(session, ctx.tenant_id)
            if users.email_exists(normalized):
                raise InvalidArgumentError("user email already exists", email=normalized)
            user = User(
                id=new_ulid(),
                tenant_id=ctx.tenant_id,
                email=normalized,
                display_name=normalized.split("@")[0],
                status="active",
                created_by=ctx.subject_id,
                updated_by=ctx.subject_id,
            )
            users.add(user)

            roles_repo = RoleRepository(session, ctx.tenant_id)
            links = UserRoleRepository(session, ctx.tenant_id)
            for role_name in roles or []:
                role = roles_repo.get_by_name(role_name)
                if role is None:
                    raise InvalidArgumentError("role not found", role=role_name)
                links.assign(user.id, role.id, created_by=ctx.subject_id)

            session.commit()
            view = self._user_view(session, user)

        self._audit(ctx, "identity.user.created", "user", user.id)
        return view

    def get_user(self, ctx: TenantContext, user_id: str) -> UserView:
        require_permission(ctx, "identity:user:read")
        self._require_active_tenant(ctx.tenant_id)
        with self._session_factory() as session:
            user = UserRepository(session, ctx.tenant_id).get(User, user_id)
            if user is None or user.deleted_at is not None:
                raise NotFoundError("User not found")
            return self._user_view(session, user)

    def list_users(self, ctx: TenantContext) -> list[UserView]:
        require_permission(ctx, "identity:user:read")
        self._require_active_tenant(ctx.tenant_id)
        with self._session_factory() as session:
            users = UserRepository(session, ctx.tenant_id).list_active()
            return [self._user_view(session, user) for user in users]

    def deactivate_user(self, ctx: TenantContext, user_id: str) -> None:
        require_permission(ctx, "identity:user:deactivate")
        self._require_active_tenant(ctx.tenant_id)
        with self._session_factory() as session:
            user = UserRepository(session, ctx.tenant_id).get(User, user_id)
            if user is None or user.deleted_at is not None:
                raise NotFoundError("User not found")
            user.deleted_at = utcnow_naive()
            user.updated_by = ctx.subject_id
            session.commit()
        self._audit(ctx, "identity.user.deactivated", "user", user_id)

    # Roles -----------------------------------------------------------------

    def create_role(
        self,
        ctx: TenantContext,
        name: str,
        permissions: set[str] | frozenset[str],
        *,
        description: str = "",
        is_system: bool = False,
    ) -> RoleView:
        require_permission(ctx, "identity:role:write")
        self._require_active_tenant(ctx.tenant_id)
        unknown = set(permissions) - IDENTITY_PERMISSIONS
        if unknown:
            raise InvalidArgumentError(
                "unknown permissions",
                permissions=sorted(unknown),
            )

        with self._session_factory() as session:
            roles = RoleRepository(session, ctx.tenant_id)
            if roles.name_exists(name):
                raise InvalidArgumentError("role already exists", role=name)
            role = Role(
                id=new_ulid(),
                tenant_id=ctx.tenant_id,
                name=name,
                description=description,
                is_system=is_system,
                created_by=ctx.subject_id,
                updated_by=ctx.subject_id,
            )
            roles.add(role)

            permissions_repo = PermissionRepository(session, ctx.tenant_id)
            permission_ids: list[str] = []
            for code in sorted(permissions):
                permission = permissions_repo.get_by_code_including_deleted(code)
                if permission is None:
                    permission = Permission(
                        id=new_ulid(),
                        tenant_id=ctx.tenant_id,
                        code=code,
                        created_by=ctx.subject_id,
                        updated_by=ctx.subject_id,
                    )
                    permissions_repo.add(permission)
                elif permission.deleted_at is not None:
                    permission.deleted_at = None
                    permission.updated_by = ctx.subject_id
                permission_ids.append(permission.id)
            RolePermissionRepository(session, ctx.tenant_id).replace(role.id, permission_ids, created_by=ctx.subject_id)
            session.commit()
            view = RoleView(
                id=role.id,
                name=role.name,
                description=role.description,
                is_system=role.is_system,
                permissions=tuple(sorted(permissions)),
            )

        self._audit(ctx, "identity.role.created", "role", role.id, detail={"role": name})
        return view

    def list_roles(self, ctx: TenantContext) -> list[RoleView]:
        require_permission(ctx, "identity:role:write")
        self._require_active_tenant(ctx.tenant_id)
        with self._session_factory() as session:
            roles = RoleRepository(session, ctx.tenant_id).list_active()
            links = RolePermissionRepository(session, ctx.tenant_id)
            permissions_repo = PermissionRepository(session, ctx.tenant_id)
            views: list[RoleView] = []
            for role in roles:
                codes: list[str] = []
                for permission_id in links.permission_ids_for_role(role.id):
                    permission = permissions_repo.get(Permission, permission_id)
                    if permission is not None:
                        codes.append(permission.code)
                views.append(
                    RoleView(
                        id=role.id,
                        name=role.name,
                        description=role.description,
                        is_system=role.is_system,
                        permissions=tuple(sorted(codes)),
                    )
                )
            return views

    def assign_role(self, ctx: TenantContext, user_id: str, role: str) -> None:
        require_permission(ctx, "identity:role:assign")
        self._require_active_tenant(ctx.tenant_id)
        with self._session_factory() as session:
            user = UserRepository(session, ctx.tenant_id).get(User, user_id)
            if user is None or user.deleted_at is not None:
                raise NotFoundError("User not found")
            role_row = RoleRepository(session, ctx.tenant_id).get_by_name(role)
            if role_row is None:
                raise InvalidArgumentError("role not found", role=role)
            UserRoleRepository(session, ctx.tenant_id).assign(user_id, role_row.id, created_by=ctx.subject_id)
            session.commit()
        self._audit(ctx, "identity.role.changed", "user", user_id, detail={"role": role, "change": "assigned"})

    def remove_role(self, ctx: TenantContext, user_id: str, role: str) -> None:
        require_permission(ctx, "identity:role:assign")
        self._require_active_tenant(ctx.tenant_id)
        with self._session_factory() as session:
            user = UserRepository(session, ctx.tenant_id).get(User, user_id)
            if user is None or user.deleted_at is not None:
                raise NotFoundError("User not found")
            role_row = RoleRepository(session, ctx.tenant_id).get_by_name(role)
            if role_row is None:
                raise InvalidArgumentError("role not found", role=role)
            UserRoleRepository(session, ctx.tenant_id).remove(user_id, role_row.id)
            session.commit()
        self._audit(ctx, "identity.role.changed", "user", user_id, detail={"role": role, "change": "removed"})

    def permissions_for_user(self, ctx: TenantContext, user_id: str) -> frozenset[str]:
        require_permission(ctx, "identity:user:read")
        self._require_active_tenant(ctx.tenant_id)
        with self._session_factory() as session:
            user = UserRepository(session, ctx.tenant_id).get(User, user_id)
            if user is None or user.deleted_at is not None:
                raise NotFoundError("User not found")
            links = UserRoleRepository(session, ctx.tenant_id)
            role_names = links.role_names_for_user(user_id)
            codes = RolePermissionRepository(session, ctx.tenant_id).permission_codes_for_roles(role_names)
            return frozenset(codes)

    def can(self, ctx: TenantContext, user_id: str, permission: str) -> bool:
        return permission in self.permissions_for_user(ctx, user_id)

    # API keys --------------------------------------------------------------

    def issue_api_key(
        self,
        ctx: TenantContext,
        *,
        name: str,
        scopes: set[str] | frozenset[str],
        expires_at: datetime | None = None,
    ) -> IssuedApiKey:
        require_permission(ctx, "identity:api_key:issue")
        self._require_active_tenant(ctx.tenant_id)
        issued = self._api_keys.issue(
            tenant_id=ctx.tenant_id,
            name=name,
            scopes=scopes,
            expires_at=expires_at,
            created_by=ctx.subject_id,
        )
        self._audit(ctx, "identity.key.issued", "api_key", issued.key_id)
        return issued

    def revoke_api_key(self, ctx: TenantContext, key_id: str) -> None:
        require_permission(ctx, "identity:api_key:revoke")
        self._require_active_tenant(ctx.tenant_id)
        record = self._api_keys.get_record(key_id)
        if record is None or record.tenant_id != ctx.tenant_id:
            raise NotFoundError("API key not found")
        self._api_keys.revoke(key_id, tenant_id=ctx.tenant_id)
        self._audit(ctx, "identity.key.revoked", "api_key", key_id)

    def rotate_api_key(self, ctx: TenantContext, key_id: str) -> IssuedApiKey:
        require_permission(ctx, "identity:api_key:rotate")
        self._require_active_tenant(ctx.tenant_id)
        record = self._api_keys.get_record(key_id)
        if record is None or record.tenant_id != ctx.tenant_id:
            raise NotFoundError("API key not found")
        issued = self._api_keys.rotate(key_id, tenant_id=ctx.tenant_id, created_by=ctx.subject_id)
        self._audit(ctx, "identity.key.rotated", "api_key", issued.key_id, detail={"previous_key_id": key_id})
        return issued

    # Auditing --------------------------------------------------------------

    def record_login(self, ctx: TenantContext, user_id: str, *, success: bool = True) -> None:
        self._require_active_tenant(ctx.tenant_id)
        self._audit(
            ctx,
            "identity.login",
            "user",
            user_id,
            status="success" if success else "failed",
        )

    def _audit(
        self,
        ctx: TenantContext,
        action: str,
        resource_type: str,
        resource_id: str,
        *,
        status: str = "success",
        detail: dict | None = None,
    ) -> None:
        if self._audit_writer is None:
            return
        event = AuditLogEvent(
            tenant_id=ctx.tenant_id,
            actor_id=ctx.subject_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            trace_id=ctx.trace_id,
            status=status,
            detail=detail or {},
        )
        try:
            self._audit_writer.write(event)
        except Exception:
            # Audit failures must never block the main request.
            AUDIT_WRITE_FAILED.inc()
            logger.exception("identity audit write failed", extra={"action": action})

    @staticmethod
    def _user_view(session: Session, user: User) -> UserView:
        role_names = UserRoleRepository(session, user.tenant_id).role_names_for_user(user.id)
        return UserView(
            id=user.id,
            tenant_id=user.tenant_id,
            email=user.email,
            display_name=user.display_name,
            status=user.status,
            roles=tuple(role_names),
        )
