"""SQL-backed identity integration tests (opt-in testcontainers)."""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import create_engine_from_dsn, make_session_factory
from app.core.errors import UnauthorizedError
from app.modules.identity.api_key import ApiKeyService, SqlApiKeyStore
from app.modules.identity.models import ApiKey


def test_sql_api_key_lifecycle_persists_only_hmac(mysql_dsn: str) -> None:
    engine = create_engine_from_dsn(mysql_dsn)
    ApiKey.__table__.create(engine)
    try:
        service = ApiKeyService(
            SqlApiKeyStore(make_session_factory(engine)),
            pepper="test-pepper",
            key_env="test",
        )
        issued = service.issue(
            tenant_id="tenant-a",
            name="ci",
            scopes={"mcp:projects:read"},
            created_by="tester",
        )
        assert service.verify(issued.raw_key).tenant_id == "tenant-a"

        with Session(engine) as session:
            row = session.scalar(select(ApiKey))
            assert row is not None
            assert row.created_by == "tester"
            assert issued.raw_key.split("_", 3)[3].encode() not in row.secret_hmac

        service.revoke(issued.key_id, tenant_id="tenant-a")
        with pytest.raises(UnauthorizedError):
            service.verify(issued.raw_key)
    finally:
        ApiKey.__table__.drop(engine)
        engine.dispose()
