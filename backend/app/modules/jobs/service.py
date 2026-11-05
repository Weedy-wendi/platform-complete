"""Job service with idempotency, retry, DLQ and scheduler locks."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import timedelta
from typing import Any, Protocol

from sqlalchemy import select, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.clock import utcnow_naive
from app.core.context import TenantContext
from app.core.errors import InvalidArgumentError, NotFoundError
from app.core.ids import new_ulid
from app.core.repository import TenantScopedRepository
from app.modules.jobs.models import DeadLetterTask, IdempotencyKey, Job, JobEvent
from app.modules.jobs.public_types import (
    CANCELLED,
    FAILED,
    QUEUED,
    RUNNING,
    SUCCEEDED,
    TIMED_OUT,
    JobEventView,
    JobSpec,
    JobView,
    TaskRunner,
    can_transition,
    is_terminal,
)
from app.modules.jobs.retry import backoff_delay


class JobService:
    def __init__(self, session_factory: sessionmaker[Session], runner: TaskRunner | None = None) -> None:
        self._session_factory = session_factory
        self._runner = runner

    def enqueue(self, ctx: TenantContext, spec: JobSpec) -> JobView:
        if not spec.job_type.strip() or not spec.idempotency_key.strip():
            raise InvalidArgumentError("job_type and idempotency_key are required")
        if spec.timeout_seconds <= 0:
            raise InvalidArgumentError("timeout_seconds must be positive")

        with self._session_factory() as session:
            existing_key = session.scalar(
                select(IdempotencyKey).where(
                    IdempotencyKey.tenant_id == ctx.tenant_id,
                    IdempotencyKey.key == spec.idempotency_key,
                )
            )
            if existing_key is not None:
                existing_job = session.get(Job, existing_key.job_id)
                if existing_job is not None:
                    return _job_view(existing_job)

            job = Job(
                id=new_ulid(),
                tenant_id=ctx.tenant_id,
                job_type=spec.job_type,
                status=QUEUED,
                payload=spec.payload,
                idempotency_key=spec.idempotency_key,
                max_attempts=3,
                created_by=ctx.subject_id,
            )
            session.add(job)
            session.add(
                IdempotencyKey(
                    id=new_ulid(),
                    tenant_id=ctx.tenant_id,
                    key=spec.idempotency_key,
                    job_id=job.id,
                )
            )
            session.add(_event(ctx.tenant_id, job.id, "queued", {"job_type": spec.job_type}))
            session.commit()
            view = _job_view(job)

        if self._runner is not None:
            self._runner.enqueue(spec)
        return view

    def start(self, ctx: TenantContext, job_id: str) -> JobView:
        return self._transition(ctx, job_id, RUNNING, "started")

    def succeed(self, ctx: TenantContext, job_id: str) -> JobView:
        with self._session_factory() as session:
            job = self._get(session, ctx, job_id)
            _require_transition(job, SUCCEEDED)
            job.status = SUCCEEDED
            job.progress = 100
            job.finished_at = utcnow_naive()
            session.add(_event(ctx.tenant_id, job.id, "succeeded"))
            session.commit()
            return _job_view(job)

    def fail(self, ctx: TenantContext, job_id: str, error: str, *, retryable: bool = True) -> JobView:
        with self._session_factory() as session:
            job = self._get(session, ctx, job_id)
            if is_terminal(job.status):
                raise InvalidArgumentError("job is already terminal", status=job.status)
            job.last_error = error
            if retryable and job.attempt + 1 < job.max_attempts:
                job.attempt += 1
                job.status = QUEUED
                session.add(
                    _event(
                        ctx.tenant_id,
                        job.id,
                        "retry",
                        {
                            "attempt": job.attempt,
                            "error": error,
                            "retry_in_seconds": round(backoff_delay(job.attempt - 1), 3),
                        },
                    )
                )
            else:
                job.status = FAILED
                job.finished_at = utcnow_naive()
                session.add(_event(ctx.tenant_id, job.id, "failed", {"error": error}))
                session.add(
                    DeadLetterTask(
                        id=new_ulid(),
                        tenant_id=ctx.tenant_id,
                        job_id=job.id,
                        job_type=job.job_type,
                        payload=job.payload,
                        error=error,
                    )
                )
            session.commit()
            return _job_view(job)

    def cancel(self, ctx: TenantContext, job_id: str) -> JobView:
        with self._session_factory() as session:
            job = self._get(session, ctx, job_id)
            _require_transition(job, CANCELLED)
            job.status = CANCELLED
            job.finished_at = utcnow_naive()
            session.add(_event(ctx.tenant_id, job.id, "cancelled"))
            session.commit()
            return _job_view(job)

    def progress(self, ctx: TenantContext, job_id: str, percent: int, message: str = "") -> JobView:
        if not 0 <= percent <= 100:
            raise InvalidArgumentError("progress must be between 0 and 100")
        with self._session_factory() as session:
            job = self._get(session, ctx, job_id)
            if is_terminal(job.status):
                raise InvalidArgumentError("job is already terminal", status=job.status)
            job.progress = percent
            session.add(_event(ctx.tenant_id, job.id, "progress", {"progress": percent, "message": message}))
            session.commit()
            return _job_view(job)

    def get(self, ctx: TenantContext, job_id: str) -> JobView:
        with self._session_factory() as session:
            return _job_view(self._get(session, ctx, job_id))

    def events(self, ctx: TenantContext, job_id: str, *, after: str | None = None) -> list[JobEventView]:
        with self._session_factory() as session:
            self._get(session, ctx, job_id)
            statement = select(JobEvent).where(
                JobEvent.tenant_id == ctx.tenant_id,
                JobEvent.job_id == job_id,
            )
            if after is not None:
                statement = statement.where(JobEvent.id > after)
            statement = statement.order_by(JobEvent.created_at, JobEvent.id)
            return [_event_view(row) for row in session.scalars(statement)]

    def event_stream(self, ctx: TenantContext, job_id: str, *, after: str | None = None) -> Iterator[JobEventView]:
        yield from self.events(ctx, job_id, after=after)

    def dead_letters(self, ctx: TenantContext, *, status: str | None = None) -> list[DeadLetterTask]:
        with self._session_factory() as session:
            statement = select(DeadLetterTask).where(DeadLetterTask.tenant_id == ctx.tenant_id)
            if status is not None:
                statement = statement.where(DeadLetterTask.status == status)
            return list(session.scalars(statement.order_by(DeadLetterTask.created_at)))

    def replay_dead_letter(self, ctx: TenantContext, dlq_id: str) -> JobView:
        with self._session_factory() as session:
            dlq = self._get_dlq(session, ctx, dlq_id)
            if dlq.status != "pending":
                raise InvalidArgumentError("dead letter is not pending", status=dlq.status)
            job = self._get(session, ctx, dlq.job_id)
            job.status = QUEUED
            job.attempt = 0
            job.last_error = None
            job.finished_at = None
            dlq.status = "replayed"
            session.add(_event(ctx.tenant_id, job.id, "replayed", {"dlq_id": dlq.id}))
            session.commit()
            return _job_view(job)

    def ignore_dead_letter(self, ctx: TenantContext, dlq_id: str) -> None:
        with self._session_factory() as session:
            dlq = self._get_dlq(session, ctx, dlq_id)
            dlq.status = "ignored"
            session.commit()

    def recover_stale(self, ctx: TenantContext, *, older_than_seconds: int = 3600) -> int:
        cutoff = utcnow_naive() - timedelta(seconds=older_than_seconds)
        with self._session_factory() as session:
            statement = select(Job).where(
                Job.tenant_id == ctx.tenant_id,
                Job.status == RUNNING,
                Job.updated_at < cutoff,
            )
            jobs = list(session.scalars(statement))
            for job in jobs:
                job.status = QUEUED
                session.add(_event(ctx.tenant_id, job.id, "recovered"))
            session.commit()
            return len(jobs)

    def claim_item(self, ctx: TenantContext, job_id: str, item_id: str, attempt: int) -> bool:
        key = f"{job_id}:{item_id}:{attempt}"
        with self._session_factory() as session:
            existing = session.scalar(
                select(IdempotencyKey).where(
                    IdempotencyKey.tenant_id == ctx.tenant_id,
                    IdempotencyKey.key == key,
                )
            )
            if existing is not None:
                return False
            session.add(
                IdempotencyKey(
                    id=new_ulid(),
                    tenant_id=ctx.tenant_id,
                    key=key,
                    job_id=job_id,
                    item_id=item_id,
                    attempt=attempt,
                )
            )
            session.commit()
            return True

    def _transition(self, ctx: TenantContext, job_id: str, target: str, event_type: str) -> JobView:
        with self._session_factory() as session:
            job = self._get(session, ctx, job_id)
            _require_transition(job, target)
            job.status = target
            if target == RUNNING:
                job.started_at = utcnow_naive()
            if target in {SUCCEEDED, FAILED, CANCELLED, TIMED_OUT}:
                job.finished_at = utcnow_naive()
            session.add(_event(ctx.tenant_id, job.id, event_type))
            session.commit()
            return _job_view(job)

    @staticmethod
    def _get(session: Session, ctx: TenantContext, job_id: str) -> Job:
        job = TenantScopedRepository(session, ctx.tenant_id).get(Job, job_id)
        if job is None:
            raise NotFoundError("Job not found")
        return job

    @staticmethod
    def _get_dlq(session: Session, ctx: TenantContext, dlq_id: str) -> DeadLetterTask:
        dlq = TenantScopedRepository(session, ctx.tenant_id).get(DeadLetterTask, dlq_id)
        if dlq is None:
            raise NotFoundError("Dead letter not found")
        return dlq


def _require_transition(job: Job, target: str) -> None:
    if not can_transition(job.status, target):
        raise InvalidArgumentError("invalid job transition", current=job.status, target=target)


def _event(tenant_id: str, job_id: str, event_type: str, payload: dict[str, Any] | None = None) -> JobEvent:
    return JobEvent(
        id=new_ulid(),
        tenant_id=tenant_id,
        job_id=job_id,
        event_type=event_type,
        payload=payload or {},
    )


def _job_view(job: Job) -> JobView:
    return JobView(
        id=job.id,
        tenant_id=job.tenant_id,
        job_type=job.job_type,
        status=job.status,
        payload=job.payload,
        attempt=job.attempt,
        max_attempts=job.max_attempts,
        progress=job.progress,
        last_error=job.last_error,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


def _event_view(row: JobEvent) -> JobEventView:
    return JobEventView(
        id=row.id,
        job_id=row.job_id,
        event_type=row.event_type,
        payload=row.payload,
        created_at=row.created_at,
    )


class SchedulerLock(Protocol):
    def acquire(self) -> bool: ...
    def release(self) -> None: ...


class InMemorySchedulerLock:
    def __init__(self) -> None:
        self._held = False

    def acquire(self) -> bool:
        if self._held:
            return False
        self._held = True
        return True

    def release(self) -> None:
        self._held = False


class MySqlSchedulerLock:
    def __init__(self, session_factory: sessionmaker[Session], name: str = "pingce-scheduler") -> None:
        self._session_factory = session_factory
        self._name = name

    def acquire(self) -> bool:
        with self._session_factory() as session:
            return bool(session.scalar(text("SELECT GET_LOCK(:name, 0)"), {"name": self._name}))

    def release(self) -> None:
        with self._session_factory() as session:
            session.scalar(text("SELECT RELEASE_LOCK(:name)"), {"name": self._name})
