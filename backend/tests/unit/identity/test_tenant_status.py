"""Tenant status checker tests (IDN-09/11)."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine

from app.core.clock import utcnow_naive
from app.core.db import make_session_factory
from app.modules.identity.models import Tenant
from app.modules.identity.tenant_status import SqlTenantStatusChecker


@pytest.fixture()
def factory():
    engine = create_engine("sqlite://")
    Tenant.__table__.create(engine)
    try:
        yield make_session_factory(engine)
    finally:
        engine.dispose()


def test_missing_tenant_can_be_allowed_for_legacy_mcp(factory) -> None:
    assert SqlTenantStatusChecker(factory).is_active("missing") is False
    assert SqlTenantStatusChecker(factory, allow_missing=True).is_active("missing") is True


def test_status_and_soft_delete_are_enforced(factory) -> None:
    with factory() as session:
        session.add(
            Tenant(
                id="tenant-a",
                name="Alpha",
                slug="alpha",
                status="active",
                created_by="test",
                updated_by="test",
            )
        )
        session.commit()

    checker = SqlTenantStatusChecker(factory)
    assert checker.is_active("tenant-a") is True

    with factory() as session:
        tenant = session.get(Tenant, "tenant-a")
        assert tenant is not None
        tenant.status = "disabled"
        session.commit()
    checker.invalidate("tenant-a")
    assert checker.is_active("tenant-a") is False

    with factory() as session:
        tenant = session.get(Tenant, "tenant-a")
        assert tenant is not None
        tenant.status = "active"
        tenant.deleted_at = utcnow_naive()
        session.commit()
    checker.invalidate("tenant-a")
    assert checker.is_active("tenant-a") is False
