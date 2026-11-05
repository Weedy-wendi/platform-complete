"""Session/transaction boundary tests (CORE-03)."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.core.db import make_session_factory, write_session
from tests.support.core_models import Widget


def _factory():
    engine = create_engine("sqlite://")
    Widget.__table__.create(engine)
    return engine, make_session_factory(engine)


def test_write_session_commits() -> None:
    engine, factory = _factory()
    with write_session(factory) as session:
        session.add(Widget(tenant_id="tenant-a", name="a"))

    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(Widget)) == 1


def test_write_session_rolls_back() -> None:
    engine, factory = _factory()
    with pytest.raises(RuntimeError):
        with write_session(factory) as session:
            session.add(Widget(tenant_id="tenant-a", name="a"))
            raise RuntimeError("boom")

    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(Widget)) == 0
