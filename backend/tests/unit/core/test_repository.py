"""Tenant-scoped repository tests (CORE-03)."""

from __future__ import annotations

import contextvars

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.context import (
    TenantContext,
    get_tenant_context,
    reset_tenant_context,
    set_tenant_context,
)
from app.core.errors import TenantRequiredError
from app.core.repository import TenantScopedRepository
from tests.support.core_models import Widget


@pytest.fixture()
def session() -> Session:
    engine = create_engine("sqlite://")
    Widget.__table__.create(engine)
    with Session(engine) as db_session:
        yield db_session


def test_repository_filters_by_tenant(session: Session) -> None:
    first = Widget(tenant_id="tenant-a", name="a")
    second = Widget(tenant_id="tenant-b", name="b")
    session.add_all([first, second])
    session.commit()

    repo = TenantScopedRepository(session, "tenant-a")
    assert [widget.name for widget in repo.list(Widget)] == ["a"]
    assert repo.get(Widget, first.id) is not None
    assert repo.get(Widget, second.id) is None

    with pytest.raises(ValueError):
        repo.add(Widget(tenant_id="tenant-b", name="c"))


def test_repository_can_read_tenant_from_context(session: Session) -> None:
    token = set_tenant_context(TenantContext(tenant_id="tenant-a", subject_id="user:1"))
    try:
        repo = TenantScopedRepository(session)
        assert repo.tenant_id == "tenant-a"
    finally:
        reset_tenant_context(token)


def test_repository_requires_a_tenant(session: Session) -> None:
    def run() -> None:
        with pytest.raises(TenantRequiredError):
            get_tenant_context()
        with pytest.raises(TenantRequiredError):
            TenantScopedRepository(session)

    contextvars.Context().run(run)
