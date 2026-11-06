"""Ingestion sync, resume, idempotency, drift and quality tests (ING-04..07)."""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import create_engine, select, update
from sqlalchemy.orm import Session, sessionmaker

from app.core.context import TenantContext
from app.core.db import Base, make_session_factory
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


class RecordingWriter:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, list[dict[str, Any]]]] = []
        self.rollbacks: list[str] = []
        self.fail = False
        self.rows: dict[str, list[dict[str, Any]]] = {}

    def write_batch(
        self,
        *,
        tenant_id: str,
        dataset_id: str,
        idempotency_key: str,
        rows: list[dict[str, Any]],
    ) -> int:
        self.calls.append((dataset_id, idempotency_key, rows))
        if self.fail:
            raise RuntimeError("catalog unavailable")
        self.rows[idempotency_key] = list(rows)
        return len(rows)

    def rollback_batch(self, *, tenant_id: str, dataset_id: str, idempotency_key: str) -> None:
        self.rollbacks.append(idempotency_key)
        self.rows.pop(idempotency_key, None)


@pytest.fixture()
def factory() -> sessionmaker[Session]:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine, tables=_TABLES)
    try:
        yield make_session_factory(engine)
    finally:
        engine.dispose()


@pytest.fixture()
def service(factory: sessionmaker[Session]) -> IngestionService:
    return IngestionService(factory)


@pytest.fixture()
def ctx() -> TenantContext:
    return TenantContext(tenant_id="tenant-a", subject_id="user:1", scopes=frozenset(), trace_id="trace-1")


def _write_csv(tmp_path, body: str) -> str:
    path = tmp_path / "samples.csv"
    path.write_text(body, encoding="utf-8")
    return str(path)


def test_sync_writes_batches_and_advances_cursor(service, ctx, tmp_path) -> None:
    path = _write_csv(tmp_path, "id,email\n1,a@example.test\n2,b@example.test\n")
    connector = service.create_connector(ctx, name="csv", kind="csv", config={"path": path})
    writer = RecordingWriter()

    result = service.sync(
        ctx,
        connector_id=connector.id,
        dataset_id="dataset-1",
        writer=writer,
        idempotency_key="job-1",
        batch_size=10,
    )

    assert result.rows_read == 2
    assert result.rows_written == 2
    assert result.rows_skipped == 0
    assert result.next_cursor.value == "2"
    assert len(writer.calls) == 1
    assert service.get_job(ctx, result.job_id)["status"] == "succeeded"
    assert service.get_cursor(ctx, connector_id=connector.id, dataset_id="dataset-1").value == "2"


def test_duplicate_delivery_is_idempotent(service, ctx, tmp_path) -> None:
    path = _write_csv(tmp_path, "id,email\n1,a@example.test\n")
    connector = service.create_connector(ctx, name="csv", kind="csv", config={"path": path})
    writer = RecordingWriter()

    first = service.sync(
        ctx,
        connector_id=connector.id,
        dataset_id="dataset-1",
        writer=writer,
        idempotency_key="same-key",
    )
    second = service.sync(
        ctx,
        connector_id=connector.id,
        dataset_id="dataset-1",
        writer=writer,
        idempotency_key="same-key",
    )

    assert first.job_id == second.job_id
    assert len(writer.calls) == 1


def test_quality_failure_does_not_write_or_advance_cursor(service, ctx, tmp_path) -> None:
    path = _write_csv(tmp_path, "id,email\n1,a@example.test\n2,\n")
    connector = service.create_connector(ctx, name="csv", kind="csv", config={"path": path})
    service.add_quality_rule(
        ctx,
        name="email required",
        rule_type="not_null",
        config={"field": "email"},
    )
    writer = RecordingWriter()

    result = service.sync(
        ctx,
        connector_id=connector.id,
        dataset_id="dataset-1",
        writer=writer,
        idempotency_key="quality-bad",
    )

    assert result.rows_written == 0
    assert writer.calls == []
    assert service.get_job(ctx, result.job_id)["status"] == "failed"
    assert service.get_cursor(ctx, connector_id=connector.id, dataset_id="dataset-1").value is None

    results = service.quality_results(ctx, result.job_id)
    assert len(results) == 1
    assert results[0].passed is False
    assert results[0].failed_rows == 1
    assert results[0].checked_rows == 2


def test_writer_failure_rolls_back_batch_and_cursor(service, ctx, tmp_path) -> None:
    path = _write_csv(tmp_path, "id,email\n1,a@example.test\n")
    connector = service.create_connector(ctx, name="csv", kind="csv", config={"path": path})
    writer = RecordingWriter()
    writer.fail = True

    result = service.sync(
        ctx,
        connector_id=connector.id,
        dataset_id="dataset-1",
        writer=writer,
        idempotency_key="write-fail",
    )

    assert result.rows_written == 0
    assert len(writer.rollbacks) == 1
    assert writer.rows == {}
    assert service.get_job(ctx, result.job_id)["status"] == "failed"
    assert service.get_cursor(ctx, connector_id=connector.id, dataset_id="dataset-1").value is None


def test_schema_drift_is_recorded_on_next_sync(service, ctx, factory, tmp_path) -> None:
    path = _write_csv(tmp_path, "id,email\n1,a@example.test\n2,b@example.test\n")
    connector = service.create_connector(ctx, name="csv", kind="csv", config={"path": path})
    writer = RecordingWriter()

    service.sync(
        ctx,
        connector_id=connector.id,
        dataset_id="dataset-1",
        writer=writer,
        idempotency_key="drift-v1",
    )

    _write_csv(tmp_path, "id,email,name\n1,a@example.test,Alice\n2,b@example.test,Bob\n")
    with factory() as session:
        session.execute(update(SyncCursor).values(value=None))
        session.commit()

    result = service.sync(
        ctx,
        connector_id=connector.id,
        dataset_id="dataset-1",
        writer=writer,
        idempotency_key="drift-v2",
    )
    job = service.get_job(ctx, result.job_id)
    assert job["status"] == "succeeded"
    assert any(alert["kind"] == "field_added" and alert["field"] == "name" for alert in job["schema_drift"])


def test_cancellation_stops_without_advancing_cursor(service, ctx, tmp_path) -> None:
    path = _write_csv(tmp_path, "id,email\n1,a@example.test\n2,b@example.test\n")
    connector = service.create_connector(ctx, name="csv", kind="csv", config={"path": path})
    writer = RecordingWriter()

    class Cancelled:
        def is_set(self) -> bool:
            return True

    result = service.sync(
        ctx,
        connector_id=connector.id,
        dataset_id="dataset-1",
        writer=writer,
        idempotency_key="cancelled",
        cancel=Cancelled(),
    )

    assert result.rows_written == 0
    assert writer.calls == []
    assert service.get_job(ctx, result.job_id)["status"] == "cancelled"
    assert service.get_cursor(ctx, connector_id=connector.id, dataset_id="dataset-1").value is None


def test_job_row_is_persisted(factory, service, ctx, tmp_path) -> None:
    path = _write_csv(tmp_path, "id\n1\n")
    connector = service.create_connector(ctx, name="csv", kind="csv", config={"path": path})
    result = service.sync(
        ctx,
        connector_id=connector.id,
        dataset_id="dataset-1",
        writer=RecordingWriter(),
        idempotency_key="persisted",
    )
    with factory() as session:
        job = session.scalar(select(IngestionJob).where(IngestionJob.id == result.job_id))
        assert job is not None
        assert job.rows_written == 1
