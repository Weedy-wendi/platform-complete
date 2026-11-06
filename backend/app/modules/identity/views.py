"""Immutable identity view objects returned by the public service."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TenantView:
    id: str
    name: str
    slug: str
    status: str


@dataclass(frozen=True)
class UserView:
    id: str
    tenant_id: str
    email: str
    display_name: str
    status: str
    roles: tuple[str, ...] = ()


@dataclass(frozen=True)
class RoleView:
    id: str
    name: str
    description: str
    is_system: bool
    permissions: tuple[str, ...] = ()
