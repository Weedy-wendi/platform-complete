"""Append-only audit account grants (AUD-02, opt-in testcontainers)."""

from __future__ import annotations

import uuid

import pymysql
import pytest
from sqlalchemy.engine import make_url

from app.core.db import create_engine_from_dsn
from app.modules.audit.models import AuditLog


def _denied(connection: pymysql.connections.Connection, sql: str) -> None:
    with pytest.raises((pymysql.err.OperationalError, pymysql.err.ProgrammingError)) as excinfo:
        with connection.cursor() as cursor:
            cursor.execute(sql)
    assert excinfo.value.args[0] == 1142


def test_audit_account_can_insert_but_not_update_or_delete(mysql_dsn: str) -> None:
    url = make_url(mysql_dsn)
    database = url.database
    user = f"audit_ro_{uuid.uuid4().hex[:8]}"
    password = "audit-test-pass"

    engine = create_engine_from_dsn(mysql_dsn)
    AuditLog.__table__.create(engine)
    root = pymysql.connect(
        host=url.host,
        port=url.port,
        user=url.username,
        password=url.password,
        database=database,
        autocommit=True,
    )
    audit = None
    try:
        with root.cursor() as cursor:
            cursor.execute(f"DROP USER IF EXISTS '{user}'@'%'")
            cursor.execute(f"CREATE USER '{user}'@'%' IDENTIFIED BY '{password}'")
            cursor.execute(f"GRANT INSERT ON `{database}`.`audit_log` TO '{user}'@'%'")
            cursor.execute("FLUSH PRIVILEGES")

        audit = pymysql.connect(
            host=url.host,
            port=url.port,
            user=user,
            password=password,
            database=database,
            charset="utf8mb4",
            autocommit=True,
        )
        _denied(audit, "SELECT COUNT(*) FROM audit_log")
        _denied(audit, "UPDATE audit_log SET status='tampered'")
        _denied(audit, "DELETE FROM audit_log")

        with audit.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO audit_log
                (id, tenant_id, actor_id, action, resource_type, resource_id,
                 trace_id, status, detail, created_at)
                VALUES
                ('audit-1', 'tenant-a', 'user:1', 'identity.login', 'user', 'user:1',
                 'trace-1', 'success', '{}', UTC_TIMESTAMP(6))
                """
            )
    finally:
        if audit is not None:
            audit.close()
        with root.cursor() as cursor:
            cursor.execute(f"DROP USER IF EXISTS '{user}'@'%'")
            cursor.execute("FLUSH PRIVILEGES")
        root.close()
        AuditLog.__table__.drop(engine)
        engine.dispose()
