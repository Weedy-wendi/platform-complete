"""Integration fixtures backed by testcontainers.

They are opt-in to keep the default suite fast and to avoid requiring Docker on
every developer machine:

    PINGCE_RUN_TESTCONTAINERS=1 pytest backend/tests/integration -q
"""

from __future__ import annotations

import os
import uuid

import pytest


def _require_testcontainers() -> None:
    if os.environ.get("PINGCE_RUN_TESTCONTAINERS") != "1":
        pytest.skip("set PINGCE_RUN_TESTCONTAINERS=1 to run testcontainers")
    pytest.importorskip("testcontainers")


@pytest.fixture(scope="session")
def mysql_container():
    _require_testcontainers()
    from testcontainers.community.mysql import MySqlContainer

    with MySqlContainer("mysql:8.0") as container:
        yield container


@pytest.fixture()
def mysql_dsn(mysql_container):
    import pymysql
    from sqlalchemy.engine import make_url

    url = make_url(mysql_container.get_connection_url())
    database = f"pingce_test_{uuid.uuid4().hex[:12]}"
    connection = pymysql.connect(
        host=url.host,
        port=url.port,
        user="root",
        password=url.password,
        autocommit=True,
    )
    try:
        with connection.cursor() as cursor:
            cursor.execute(f"CREATE DATABASE `{database}` CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci")
        yield (f"mysql+pymysql://root:{url.password}@{url.host}:{url.port}/{database}?charset=utf8mb4")
    finally:
        with connection.cursor() as cursor:
            cursor.execute(f"DROP DATABASE IF EXISTS `{database}`")
        connection.close()


@pytest.fixture(scope="session")
def redis_container():
    _require_testcontainers()
    from testcontainers.community.redis import RedisContainer

    with RedisContainer("redis:7-alpine") as container:
        yield container


@pytest.fixture()
def redis_dsn(redis_container):
    host = redis_container.get_container_host_ip()
    port = redis_container.get_exposed_port(6379)
    return f"redis://{host}:{port}/0"


@pytest.fixture()
def redis_namespace() -> str:
    """Unique per-test key prefix so parallel tests never share keys."""
    return f"pingce:test:{uuid.uuid4().hex}:"


@pytest.fixture()
def redis_client(redis_dsn: str, redis_namespace: str):
    """Redis client whose keys are namespaced and flushed after the test."""
    import redis

    client = redis.Redis.from_url(redis_dsn)
    try:
        yield client
    finally:
        keys = list(client.scan_iter(match=f"{redis_namespace}*", count=500))
        if keys:
            client.delete(*keys)
        client.close()
