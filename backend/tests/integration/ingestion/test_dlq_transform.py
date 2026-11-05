"""DLQ replay, field transforms and stable dedupe tests (ING-09)."""

from __future__ import annotations

import json
from typing import Any

import pytest
from sqlalchemy import create_engine

from app.core.context import TenantContext
from app.core.db import Base, make_session_factory
from app.core.errors import InvalidArgumentError
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
        self.rows: list[dict[str, Any]] = []
        self.fail = False

    def write_batch(
        self,
        *,
        tenant_id: str,
        dataset_id: str,
        idempotency_key: str,
        rows: list[dict[str, Any]],
    ) -> int:
        if self.fail:
            raise RuntimeError("catalog unavailable")
        self.rows.extend(rows)
        return len(rows)

    def rollback_batch(self, *, tenant_id: str, dataset_id: str, idempotency_key: str) -> None:
        return None


@pytest.fixture()
def factory():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine, tables=_TABLES)
    try:
        yield make_session_factory(engine)
    finally:
        engine.dispose()


@pytest.fixture()
def service(factory) -> IngestionService:
    return IngestionService(factory)


@pytest.fixture()
def ctx() -> TenantContext:
    return TenantContext(tenant_id="tenant-a", subject_id="user:1", trace_id="trace-1")


def _write(tmp_path, name: str, body: str) -> str:
    path = tmp_path / name
    path.write_text(body, encoding="utf-8")
    return str(path)


def test_quality_failure_records_one_dead_letter(service, ctx, tmp_path) -> None:
    path = _write(tmp_path, "samples.csv", "id,email\n1,a@example.test\n2,\n")
    connector = service.create_connector(ctx, name="csv", kind="csv", config={"path": path})
    service.add_quality_rule(ctx, name="email required", rule_type="not_null", config={"field": "email"})

    result = service.sync(
        ctx,
        connector_id=connector.id,
        dataset_id="dataset-1",
        writer=RecordingWriter(),
        idempotency_key="quality-bad",
    )

    letters = service.dead_letters(ctx)
    assert len(letters) == 1
    letter = letters[0]
    assert letter["job_id"] == result.job_id
    assert letter["connector_id"] == connector.id
    assert letter["payload"]["dataset_id"] == "dataset-1"
    assert "quality" in letter["reason"]
    assert letter["replayed"] is False

    # Re-running the same idempotency key does not duplicate the dead letter.
    service.sync(
        ctx,
        connector_id=connector.id,
        dataset_id="dataset-1",
        writer=RecordingWriter(),
        idempotency_key="quality-bad",
    )
    assert len(service.dead_letters(ctx)) == 1


def test_read_exception_records_dead_letter(service, ctx, tmp_path) -> None:
    connector = service.create_connector(
        ctx,
        name="broken",
        kind="csv",
        config={"path": str(tmp_path / "missing.csv")},
    )

    result = service.sync(
        ctx,
        connector_id=connector.id,
        dataset_id="dataset-1",
        writer=RecordingWriter(),
        idempotency_key="read-fail",
    )

    letters = service.dead_letters(ctx)
    assert len(letters) == 1
    assert letters[0]["job_id"] == result.job_id
    assert service.get_job(ctx, result.job_id)["status"] == "failed"


def test_replay_returns_runnable_job(service, ctx, tmp_path) -> None:
    path = _write(tmp_path, "samples.csv", "id,email\n1,a@example.test\n")
    connector = service.create_connector(ctx, name="csv", kind="csv", config={"path": path})
    writer = RecordingWriter()
    writer.fail = True

    failed = service.sync(
        ctx,
        connector_id=connector.id,
        dataset_id="dataset-1",
        writer=writer,
        idempotency_key="write-fail",
    )
    letter = service.dead_letters(ctx)[0]

    replayed_job_id = service.replay_dead_letter(ctx, letter["id"])

    assert replayed_job_id != failed.job_id
    assert service.dead_letters(ctx)[0]["replayed"] is True
    with pytest.raises(InvalidArgumentError):
        service.replay_dead_letter(ctx, letter["id"])

    writer.fail = False
    replayed = service.sync(
        ctx,
        connector_id=connector.id,
        dataset_id="dataset-1",
        writer=writer,
        idempotency_key=replayed_job_id,
    )
    assert replayed.job_id == replayed_job_id
    assert replayed.rows_written == 1
    assert service.get_job(ctx, replayed_job_id)["status"] == "succeeded"


def test_field_transform_applies_before_write(service, ctx, tmp_path) -> None:
    path = _write(
        tmp_path,
        "people.jsonl",
        json.dumps({"full_name": "Alice", "contact": "alice@example.test", "age": "31"}) + "\n",
    )
    connector = service.create_connector(
        ctx,
        name="people",
        kind="jsonl",
        config={"path": path},
        transform={
            "name": "full_name",
            "email": {"from": "contact", "mask": "email"},
            "age": {"from": "age", "type": "integer"},
        },
    )
    writer = RecordingWriter()

    result = service.sync(
        ctx,
        connector_id=connector.id,
        dataset_id="dataset-1",
        writer=writer,
        idempotency_key="transform",
    )

    assert result.rows_read == 1
    assert result.rows_written == 1
    assert writer.rows == [
        {
            "full_name": "Alice",
            "contact": "alice@example.test",
            "name": "Alice",
            "email": "a***@example.test",
            "age": 31,
        }
    ]


def test_duplicate_rows_are_skipped_by_stable_key(service, ctx, tmp_path) -> None:
    body = "\n".join(
        [
            json.dumps({"id": "1", "value": "a"}),
            json.dumps({"id": "1", "value": "a"}),
            json.dumps({"id": "2", "value": "b"}),
            json.dumps({"id": "2", "value": "b"}),
        ]
    )
    path = _write(tmp_path, "dupes.jsonl", body + "\n")
    connector = service.create_connector(
        ctx,
        name="dupes",
        kind="jsonl",
        config={"path": path},
        dedupe_key="id",
    )
    writer = RecordingWriter()

    result = service.sync(
        ctx,
        connector_id=connector.id,
        dataset_id="dataset-1",
        writer=writer,
        idempotency_key="dedupe",
    )

    assert result.rows_read == 4
    assert result.rows_written == 2
    assert result.rows_skipped == 2
    assert [row["id"] for row in writer.rows] == ["1", "2"]
