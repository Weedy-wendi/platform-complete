"""SQL logging tests (CORE-10)."""

from __future__ import annotations

import json
import logging

from sqlalchemy import text

from app.core.context import (
    Principal,
    TenantContext,
    reset_principal,
    reset_tenant_context,
    set_principal,
    set_tenant_context,
)
from app.core.db import create_engine_from_dsn
from app.core.logging import JsonFormatter


def test_sql_log_carries_context_and_omits_parameters(caplog) -> None:
    engine = create_engine_from_dsn("sqlite://")
    token = set_tenant_context(TenantContext(tenant_id="tenant-a", subject_id="user:1", trace_id="trace-1"))
    try:
        with caplog.at_level(logging.INFO, logger="app.core.sql"):
            with engine.connect() as connection:
                connection.execute(text("SELECT :value AS v"), {"value": "super-secret-value"})
    finally:
        reset_tenant_context(token)
        engine.dispose()

    records = [record for record in caplog.records if record.name == "app.core.sql"]
    assert records
    record = records[-1]
    assert "SELECT" in record.sql
    assert "super-secret-value" not in record.sql
    assert record.tenant_id == "tenant-a"
    assert record.trace_id == "trace-1"

    payload = json.loads(JsonFormatter().format(record))
    assert payload["tenant_id"] == "tenant-a"
    assert payload["trace_id"] == "trace-1"
    assert "super-secret-value" not in payload["sql"]


def test_formatter_falls_back_to_tenant_context() -> None:
    token = set_tenant_context(TenantContext(tenant_id="tenant-b", subject_id="user:2", trace_id="trace-2"))
    try:
        record = logging.LogRecord("unit", logging.INFO, __file__, 1, "hello", None, None)
        payload = json.loads(JsonFormatter().format(record))
    finally:
        reset_tenant_context(token)

    assert payload["tenant_id"] == "tenant-b"
    assert payload["trace_id"] == "trace-2"


def test_formatter_still_uses_principal_when_no_tenant_context() -> None:
    principal = Principal(tenant_id="tenant-c", subject="user:3", scopes=frozenset())
    token = set_principal(principal)
    try:
        record = logging.LogRecord("unit", logging.INFO, __file__, 1, "hello", None, None)
        payload = json.loads(JsonFormatter().format(record))
    finally:
        reset_principal(token)

    assert payload["tenant_id"] == "tenant-c"
