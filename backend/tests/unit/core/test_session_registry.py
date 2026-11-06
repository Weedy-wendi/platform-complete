"""Platform read/write routing tests (CORE-08)."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.db import (
    SessionRegistry,
    get_session_registry,
    make_session_factory,
    reset_session_registry,
    set_session_registry,
)
from tests.support.core_models import Widget


def _sqlite_registry(*, replica: bool) -> tuple[SessionRegistry, object, object]:
    write_engine = create_engine("sqlite://")
    Widget.__table__.create(write_engine)
    read_engine = create_engine("sqlite://") if replica else write_engine
    if replica:
        Widget.__table__.create(read_engine)
    registry = SessionRegistry(
        write_engine=write_engine,
        read_engine=read_engine,
        write_factory=make_session_factory(write_engine),
        read_factory=make_session_factory(read_engine),
    )
    return registry, write_engine, read_engine


def test_read_falls_back_to_write_engine_without_replica() -> None:
    registry, write_engine, read_engine = _sqlite_registry(replica=False)
    try:
        assert registry.read_engine is registry.write_engine
        with registry.write_session() as session:
            session.add(Widget(tenant_id="tenant-a", name="a"))

        with registry.read_session() as session:
            assert session.scalar(select(func.count()).select_from(Widget)) == 1
    finally:
        registry.dispose()
        write_engine.dispose()
        read_engine.dispose()


def test_reads_and_writes_route_to_separate_engines() -> None:
    registry, write_engine, read_engine = _sqlite_registry(replica=True)
    try:
        assert registry.read_engine is not registry.write_engine
        with registry.write_session() as session:
            session.add(Widget(tenant_id="tenant-a", name="a"))

        # The replica is a separate database in this test, so it stays empty.
        with registry.read_session() as session:
            assert session.scalar(select(func.count()).select_from(Widget)) == 0
        with Session(write_engine) as session:
            assert session.scalar(select(func.count()).select_from(Widget)) == 1
    finally:
        registry.dispose()
        write_engine.dispose()
        read_engine.dispose()


def test_from_settings_requires_a_database_url() -> None:
    with pytest.raises(ValueError):
        SessionRegistry.from_settings(Settings(database_url=""))


def test_from_settings_uses_replica_when_configured() -> None:
    registry = SessionRegistry.from_settings(
        Settings(
            database_url="sqlite://",
            read_replica_url="sqlite://",
        )
    )
    try:
        assert registry.read_engine is not registry.write_engine
    finally:
        registry.dispose()


def test_registry_accessor_is_lazy_and_replaceable() -> None:
    reset_session_registry()
    registry, write_engine, read_engine = _sqlite_registry(replica=False)
    set_session_registry(registry)
    try:
        assert get_session_registry() is registry
    finally:
        reset_session_registry()
        registry.dispose()
        write_engine.dispose()
        read_engine.dispose()


def test_read_replica_requires_database_url() -> None:
    with pytest.raises(ValueError):
        Settings(database_url="", read_replica_url="sqlite://")


def test_read_database_url_falls_back() -> None:
    assert Settings(database_url="sqlite://write").read_database_url == "sqlite://write"
    settings = Settings(database_url="sqlite://write", read_replica_url="sqlite://read")
    assert settings.read_database_url == "sqlite://read"
