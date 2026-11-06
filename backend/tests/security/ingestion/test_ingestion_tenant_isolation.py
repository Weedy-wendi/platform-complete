"""Ingestion tenant isolation tests."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.context import TenantContext
from app.core.db import Base, make_session_factory
from app.core.errors import NotFoundError
from app.modules.ingestion.models import (
    ConnectorRecord,
    IngestionDeadLetter,
    IngestionJob,
    QualityResult,
    QualityRule,
    SyncCursor,
)
from app.modules.ingestion.service import IngestionService

_TABLES = [
    ConnectorRecord.__table__,
    IngestionJob.__table__,
    SyncCursor.__table__,
    QualityRule.__table__,
    QualityResult.__table__,
    IngestionDeadLetter.__table__,
]


@pytest.fixture()
def factory() -> sessionmaker[Session]:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine, tables=_TABLES)
    try:
        yield make_session_factory(engine)
    finally:
        engine.dispose()


def test_cross_tenant_connector_and_job_are_not_found(factory, tmp_path) -> None:
    service = IngestionService(factory)
    tenant_a = TenantContext(tenant_id="tenant-a", subject_id="user:1")
    tenant_b = TenantContext(tenant_id="tenant-b", subject_id="user:2")
    path = tmp_path / "samples.csv"
    path.write_text("id\n1\n", encoding="utf-8")

    connector = service.create_connector(tenant_a, name="csv", kind="csv", config={"path": str(path)})
    with pytest.raises(NotFoundError):
        service.get_connector(tenant_b, connector.id)

    class Writer:
        def write_batch(self, *, tenant_id, dataset_id, idempotency_key, rows):
            return len(rows)

        def rollback_batch(self, *, tenant_id, dataset_id, idempotency_key):
            return None

    result = service.sync(
        tenant_a,
        connector_id=connector.id,
        dataset_id="dataset-1",
        writer=Writer(),
        idempotency_key="job-a",
    )
    with pytest.raises(NotFoundError):
        service.get_job(tenant_b, result.job_id)
    with pytest.raises(NotFoundError):
        service.quality_results(tenant_b, result.job_id)
    with pytest.raises(NotFoundError):
        service.sync(
            tenant_b,
            connector_id=connector.id,
            dataset_id="dataset-1",
            writer=Writer(),
            idempotency_key="job-b",
        )
