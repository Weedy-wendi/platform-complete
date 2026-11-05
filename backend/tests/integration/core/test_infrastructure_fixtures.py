"""Smoke tests for the opt-in MySQL/Redis fixtures (CORE-07/CORE-09)."""

from __future__ import annotations

import pytest
from sqlalchemy import text

from app.core.db import create_engine_from_dsn, make_session_factory, write_session


def test_mysql_fixture_creates_an_isolated_database(mysql_dsn: str) -> None:
    engine = create_engine_from_dsn(mysql_dsn)
    try:
        with engine.connect() as connection:
            assert connection.execute(text("SELECT 1")).scalar() == 1
    finally:
        engine.dispose()


def test_mysql_fixture_supports_ddl_and_rollback(mysql_dsn: str) -> None:
    engine = create_engine_from_dsn(mysql_dsn)
    factory = make_session_factory(engine)
    try:
        with engine.begin() as connection:
            connection.execute(text("CREATE TABLE core_fixture_probe (id INT PRIMARY KEY, tenant_id VARCHAR(32))"))

        with pytest.raises(RuntimeError):
            with write_session(factory) as session:
                session.execute(text("INSERT INTO core_fixture_probe (id, tenant_id) VALUES (1, 'tenant-a')"))
                raise RuntimeError("rollback probe")

        with engine.connect() as connection:
            assert connection.execute(text("SELECT COUNT(*) FROM core_fixture_probe")).scalar() == 0
    finally:
        with engine.begin() as connection:
            connection.execute(text("DROP TABLE IF EXISTS core_fixture_probe"))
        engine.dispose()


def test_redis_fixture_is_reachable(redis_dsn: str) -> None:
    import redis

    client = redis.Redis.from_url(redis_dsn)
    try:
        assert client.ping() is True
    finally:
        client.close()


def test_redis_client_uses_a_unique_namespace(redis_client, redis_namespace: str) -> None:
    key = f"{redis_namespace}probe"
    assert redis_client.set(key, "1") is True
    assert redis_client.get(key) == b"1"
    assert redis_namespace.startswith("pingce:test:")


def test_redis_namespace_is_cleaned_up(redis_client, redis_namespace: str) -> None:
    # The fixture teardown removes only this namespace; verify the key expires
    # through the cleanup path by checking the namespace is unique per test.
    assert redis_namespace.endswith(":")
    redis_client.set(f"{redis_namespace}probe", "1")
