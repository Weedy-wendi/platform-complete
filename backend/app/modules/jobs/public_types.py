"""Jobs public DTOs and state machine."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol

from app.core.context import TenantContext

QUEUED = "queued"
RUNNING = "running"
SUCCEEDED = "succeeded"
FAILED = "failed"
CANCELLED = "cancelled"
TIMED_OUT = "timed_out"

_TERMINAL = {SUCCEEDED, FAILED, CANCELLED, TIMED_OUT}
_ALLOWED = {
    QUEUED: {RUNNING, CANCELLED, FAILED},
    RUNNING: {SUCCEEDED, FAILED, CANCELLED, TIMED_OUT},
    SUCCEEDED: set(),
    FAILED: set(),
    CANCELLED: set(),
    TIMED_OUT: set(),
}


def can_transition(current: str, target: str) -> bool:
    return target in _ALLOWED.get(current, set())


def is_terminal(status: str) -> bool:
    return status in _TERMINAL


@dataclass(frozen=True)
class JobSpec:
    job_type: str
    payload: dict[str, Any]
    idempotency_key: str
    timeout_seconds: int = 3600


@dataclass(frozen=True)
class JobView:
    id: str
    tenant_id: str
    job_type: str
    status: str
    payload: dict[str, Any]
    attempt: int
    max_attempts: int
    progress: int
    last_error: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True)
class JobEventView:
    id: str
    job_id: str
    event_type: str
    payload: dict[str, Any] = field(default_factory=dict)
    created_at: datetime | None = None


class JobHandler(Protocol):
    def handle(self, job: JobView) -> None: ...


class TaskRunner(Protocol):
    def enqueue(self, spec: JobSpec) -> str: ...
    def cancel(self, job_id: str, ctx: TenantContext) -> None: ...
