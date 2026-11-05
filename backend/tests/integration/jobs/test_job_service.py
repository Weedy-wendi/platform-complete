"""Jobs state machine, idempotency, retry, DLQ, progress (JOB-01..06)."""

from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import create_engine

from app.core.clock import utcnow_naive
from app.core.context import TenantContext
from app.core.db import Base, make_session_factory
from app.core.errors import InvalidArgumentError, NotFoundError
from app.modules.jobs.models import DeadLetterTask, IdempotencyKey, Job, JobEvent
from app.modules.jobs.public_types import CANCELLED, QUEUED, RUNNING, SUCCEEDED, JobSpec
from app.modules.jobs.service import InMemorySchedulerLock, JobService

_TABLES = [Job.__table__, JobEvent.__table__, DeadLetterTask.__table__, IdempotencyKey.__table__]


@pytest.fixture()
def factory():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine, tables=_TABLES)
    try:
        yield make_session_factory(engine)
    finally:
        engine.dispose()


@pytest.fixture()
def service(factory) -> JobService:
    return JobService(factory)


@pytest.fixture()
def ctx() -> TenantContext:
    return TenantContext(tenant_id="tenant-a", subject_id="worker", scopes=frozenset(), trace_id="trace-1")


def _spec(key: str = "key-1") -> JobSpec:
    return JobSpec(job_type="evaluation.run", payload={"run_id": "run-1"}, idempotency_key=key)


def test_duplicate_enqueue_is_idempotent(service: JobService, ctx: TenantContext) -> None:
    first = service.enqueue(ctx, _spec())
    second = service.enqueue(ctx, _spec())
    assert first.id == second.id
    assert first.status == QUEUED


def test_state_machine_and_events(service: JobService, ctx: TenantContext) -> None:
    job = service.enqueue(ctx, _spec())
    with pytest.raises(InvalidArgumentError):
        service.succeed(ctx, job.id)
    service.start(ctx, job.id)
    service.progress(ctx, job.id, 40, "halfway")
    done = service.succeed(ctx, job.id)
    assert done.status == SUCCEEDED
    assert done.progress == 100
    event_types = [event.event_type for event in service.events(ctx, job.id)]
    assert event_types == ["queued", "started", "progress", "succeeded"]


def test_cancel_and_illegal_transition(service: JobService, ctx: TenantContext) -> None:
    job = service.enqueue(ctx, _spec())
    cancelled = service.cancel(ctx, job.id)
    assert cancelled.status == CANCELLED
    with pytest.raises(InvalidArgumentError):
        service.start(ctx, job.id)


def test_retry_exhaustion_creates_dlq_and_replay(service: JobService, ctx: TenantContext) -> None:
    job = service.enqueue(ctx, _spec())
    for _ in range(2):
        service.start(ctx, job.id)
        failed = service.fail(ctx, job.id, "transient", retryable=True)
        assert failed.status == QUEUED
    service.start(ctx, job.id)
    service.fail(ctx, job.id, "final", retryable=True)

    letters = service.dead_letters(ctx, status="pending")
    assert len(letters) == 1
    assert letters[0].job_id == job.id

    replayed = service.replay_dead_letter(ctx, letters[0].id)
    assert replayed.status == QUEUED
    service.start(ctx, job.id)
    assert service.succeed(ctx, job.id).status == SUCCEEDED
    assert service.dead_letters(ctx)[0].status == "replayed"


def test_non_retryable_failure_goes_straight_to_dlq(service: JobService, ctx: TenantContext) -> None:
    job = service.enqueue(ctx, _spec())
    service.start(ctx, job.id)
    failed = service.fail(ctx, job.id, "bad input", retryable=False)
    assert failed.status == "failed"
    assert len(service.dead_letters(ctx)) == 1


def test_item_idempotency_claim(service: JobService, ctx: TenantContext) -> None:
    job = service.enqueue(ctx, _spec())
    assert service.claim_item(ctx, job.id, "item-1", 0) is True
    assert service.claim_item(ctx, job.id, "item-1", 0) is False
    assert service.claim_item(ctx, job.id, "item-1", 1) is True


def test_recover_stale_running_job(service: JobService, ctx: TenantContext, factory) -> None:
    job = service.enqueue(ctx, _spec())
    service.start(ctx, job.id)
    with factory() as session:
        row = session.get(Job, job.id)
        assert row is not None
        row.updated_at = utcnow_naive() - timedelta(hours=2)
        session.commit()
    assert service.recover_stale(ctx, older_than_seconds=3600) == 1
    assert service.get(ctx, job.id).status == QUEUED


def test_cross_tenant_job_is_not_visible(service: JobService, ctx: TenantContext) -> None:
    job = service.enqueue(ctx, _spec())
    other = TenantContext(tenant_id="tenant-b", subject_id="worker", scopes=frozenset(), trace_id="trace-2")
    with pytest.raises(NotFoundError):
        service.get(other, job.id)
    with pytest.raises(NotFoundError):
        service.cancel(other, job.id)


def test_scheduler_lock_is_singleton() -> None:
    lock = InMemorySchedulerLock()
    assert lock.acquire() is True
    assert lock.acquire() is False
    lock.release()
    assert lock.acquire() is True


def test_state_machine_predicate() -> None:
    from app.modules.jobs.public_types import can_transition, is_terminal

    assert can_transition(RUNNING, SUCCEEDED) is True
    assert can_transition(SUCCEEDED, RUNNING) is False
    assert is_terminal(SUCCEEDED) is True
