"""Tenant status checks used at authentication boundaries."""

from __future__ import annotations

import time
from typing import Protocol

from sqlalchemy.orm import Session, sessionmaker

from app.modules.identity.models import Tenant


class TenantStatusChecker(Protocol):
    def is_active(self, tenant_id: str) -> bool: ...


class SqlTenantStatusChecker:
    """Caches tenant status for at most 60 seconds.

    A disabled tenant therefore stops authenticating within the same window as
    an API-key revocation. ``invalidate`` is called explicitly on status change.
    """

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        ttl_seconds: int = 60,
        allow_missing: bool = False,
    ) -> None:
        if not 0 < ttl_seconds <= 60:
            raise ValueError("ttl_seconds must be between 1 and 60")
        self._session_factory = session_factory
        self._ttl = ttl_seconds
        self._allow_missing = allow_missing
        self._cache: dict[str, tuple[bool, float]] = {}

    def is_active(self, tenant_id: str) -> bool:
        now = time.time()
        cached = self._cache.get(tenant_id)
        if cached is not None and cached[1] > now:
            return cached[0]

        with self._session_factory() as session:
            tenant = session.get(Tenant, tenant_id)
            if tenant is None:
                active = self._allow_missing
            else:
                active = tenant.status == "active" and tenant.deleted_at is None
        self._cache[tenant_id] = (active, now + self._ttl)
        return active

    def invalidate(self, tenant_id: str) -> None:
        self._cache.pop(tenant_id, None)
