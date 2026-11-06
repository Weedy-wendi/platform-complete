"""Explicit 14-category edge matrix (016-quality-guardrails FR-005).

Every category from ``docs/architecture/edge-cases.md`` section 1 has at least
one in-process test. All persistence uses SQLite and fakes; no external service
is contacted, so the whole module stays far below the 10-minute CI budget.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine

from app.api.memory import InMemoryProjects
from app.api.pagination import CursorCodec, page_records
from app.api.schemas import BadcaseSearchIn, EvaluatorMetricIn, ProjectCreate
from app.core.clock import to_iso, utcnow_naive
from app.core.context import TenantContext
from app.core.db import Base, make_session_factory
from app.core.errors import (
    InvalidArgumentError,
    NotFoundError,
    UpstreamUnavailableError,
)
from app.modules.assets.storage import build_key
from app.modules.audit.public import sanitize_detail
from app.modules.evaluation.models import (
    Baseline,
    EvalSuite,
    Evaluator,
    EvaluatorVersion,
    JudgeCall,
    Metric,
    Run,
    RunItem,
    Score,
    SuiteVersion,
    Target,
)
from app.modules.evaluation.service import EvaluationService
from app.modules.evaluation.types import AgentRequest, AgentResponse, SampleInput, StartRunRequest
from app.modules.jobs.models import DeadLetterTask, IdempotencyKey, Job, JobEvent
from app.modules.jobs.public_types import JobSpec
from app.modules.jobs.service import JobService
from app.modules.model_gateway.policy import CircuitBreaker

_TABLES = [
    Job.__table__,
    JobEvent.__table__,
    DeadLetterTask.__table__,
    IdempotencyKey.__table__,
    Evaluator.__table__,
    EvaluatorVersion.__table__,
    Metric.__table__,
    EvalSuite.__table__,
    SuiteVersion.__table__,
    Target.__table__,
    Run.__table__,
    RunItem.__table__,
    Score.__table__,
    JudgeCall.__table__,
    Baseline.__table__,
]

_EVALUATOR = {
    "id": "ev-accuracy",
    "name": "exact",
    "kind": "rule",
    "rule": "exact_match",
    "metric": {"name": "accuracy", "direction": "higher_is_better"},
}
_METRICS = [{"name": "accuracy", "direction": "higher_is_better"}]
_TARGET = {"adapter": "fake", "model": "fake-1", "temperature": 0.0, "seed": 7}


@pytest.fixture()
def factory():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine, tables=_TABLES)
    try:
        yield make_session_factory(engine)
    finally:
        engine.dispose()


@pytest.fixture()
def ctx() -> TenantContext:
    return TenantContext(tenant_id="tenant-a", subject_id="qa", scopes=frozenset(), trace_id="edge-trace")


class _EdgeAdapter:
    """Deterministic target that can fail or time out per sample."""

    def __init__(self, *, fail_on: set[str] | None = None, timeout_on: set[str] | None = None) -> None:
        self.fail_on = fail_on or set()
        self.timeout_on = timeout_on or set()
        self.calls: list[str] = []

    def invoke(self, ctx: TenantContext, request: AgentRequest) -> AgentResponse:
        self.calls.append(request.sample_key)
        if request.sample_key in self.timeout_on:
            raise TimeoutError(f"upstream timed out for {request.sample_key}")
        if request.sample_key in self.fail_on:
            raise RuntimeError(f"upstream failed for {request.sample_key}")
        return AgentResponse(output=str(request.expected or ""), trace_id=f"trace-{request.sample_key}")


def _start_request(*sample_keys: str, client_request_id: str = "edge-request") -> StartRunRequest:
    samples = tuple(SampleInput(key, {"input": f"question {key}"}, expected="yes") for key in sample_keys)
    return StartRunRequest(
        client_request_id=client_request_id,
        dataset_id="dataset-1",
        dataset_version=1,
        dataset_hash="a" * 64,
        samples=samples,
        target_config=dict(_TARGET),
        evaluator_versions=(dict(_EVALUATOR),),
        metric_configs=tuple(dict(item) for item in _METRICS),
        sampling={"strategy": "full", "seed": 42},
        code_version="edge",
        adapter_version="1",
        target_config_version="1",
        mode="record",
        env="test",
    )


def _page(records: list[dict[str, str]]) -> Any:
    return page_records(
        records,
        limit=10,
        cursor=None,
        codec=CursorCodec("edge-secret"),
        tenant_id="tenant-a",
        route="edge",
        query_hash="q",
        key_fn=lambda item: item["id"],
    )


# Category 1 - zero/empty: empty inputs are explicit results, never a silent pass.
def test_zero_empty_pagination_and_run_creation(factory, ctx) -> None:
    page = _page([])
    assert page.items == []
    assert page.next_cursor is None

    service = EvaluationService(factory)
    with pytest.raises(InvalidArgumentError):
        service.start_run(ctx, _start_request())


# Category 2 - singleton/min: the smallest valid input still works.
def test_singleton_minimum_page() -> None:
    page = _page([{"id": "only"}])
    assert [item["id"] for item in page.items] == ["only"]
    assert page.next_cursor is None


# Category 3 - limits/overflow: max+1 and overlong strings are rejected.
def test_limits_and_overflow_are_rejected() -> None:
    with pytest.raises(ValidationError):
        ProjectCreate.model_validate({"name": "x" * 129})
    with pytest.raises(ValidationError):
        BadcaseSearchIn.model_validate({"limit": 51})


# Category 4 - duplicate/idempotency: the same logical request maps to one job.
def test_duplicate_enqueue_is_idempotent(factory, ctx) -> None:
    service = JobService(factory)
    spec = JobSpec("evaluation.run", {}, "edge-idempotency")
    assert service.enqueue(ctx, spec).id == service.enqueue(ctx, spec).id


# Category 5 - concurrency/race: item claims are atomic, exactly one winner.
def test_concurrent_item_claim_has_one_winner(factory, ctx) -> None:
    service = JobService(factory)
    job = service.enqueue(ctx, JobSpec("evaluation.run", {}, "edge-claim"))
    assert service.claim_item(ctx, job.id, "item-1", 0) is True
    assert service.claim_item(ctx, job.id, "item-1", 0) is False
    assert service.claim_item(ctx, job.id, "item-1", 1) is True


# Category 6 - partial failure: completed items are kept and counted.
def test_partial_failure_keeps_completed_items(factory, ctx) -> None:
    service = EvaluationService(factory)
    run = service.start_run(ctx, _start_request("s1", "s2", "s3"))
    view = service.execute(ctx, run.run_id, adapter=_EdgeAdapter(fail_on={"s2"}))

    assert view.status == "succeeded"
    assert (view.succeeded_items, view.failed_items) == (2, 1)
    statuses = {item.sample_key: item.status for item in service.list_items(ctx, run.run_id).items}
    assert statuses == {"s1": "succeeded", "s2": "failed", "s3": "succeeded"}


# Category 7 - timeout/cancel: a timeout fails the item without losing the run record.
def test_timeout_is_recorded_per_item(factory, ctx) -> None:
    service = EvaluationService(factory)
    run = service.start_run(ctx, _start_request("slow"))
    view = service.execute(ctx, run.run_id, adapter=_EdgeAdapter(timeout_on={"slow"}))

    assert view.status == "failed"
    item = service.list_items(ctx, run.run_id).items[0]
    assert item.status == "failed"
    assert item.error is not None and "TimeoutError" in item.error


# Category 8 - dependency failure: the breaker fails fast instead of retrying forever.
def test_dependency_failure_opens_circuit() -> None:
    breaker = CircuitBreaker(failure_threshold=1, recovery_seconds=60, clock=lambda: 0)
    breaker.before_call()
    breaker.record_failure()
    assert breaker.state == "open"
    with pytest.raises(UpstreamUnavailableError):
        breaker.before_call()


# Category 9 - malicious/adversarial: traversal and injection payloads stay inert.
def test_path_traversal_and_injection_are_rejected_or_inert() -> None:
    with pytest.raises(InvalidArgumentError):
        build_key(tenant_id="t", asset_type="dataset", asset_id="d", version="v", filename="../etc/passwd")
    with pytest.raises(InvalidArgumentError):
        build_key(tenant_id="t", asset_type="dataset", asset_id="d", version="v", filename="..\\secret")

    ctx = TenantContext(tenant_id="tenant-a", subject_id="qa", scopes=frozenset(), trace_id="edge")
    projects = InMemoryProjects()
    payload = "'; DROP TABLE project; --"
    projects.create_project(ctx, name=payload)
    assert [record.name for record in projects.list_projects(ctx, cursor=None, limit=10).items] == [payload]


# Category 10 - lifecycle: retries exhaust into the dead-letter queue exactly once.
def test_retry_exhaustion_reaches_dead_letter(factory, ctx) -> None:
    service = JobService(factory)
    job = service.enqueue(ctx, JobSpec("evaluation.run", {}, "edge-lifecycle"))
    for _ in range(3):
        service.start(ctx, job.id)
        service.fail(ctx, job.id, "boom", retryable=True)

    view = service.get(ctx, job.id)
    assert view.status == "failed"
    dead_letters = service.dead_letters(ctx)
    assert len(dead_letters) == 1
    assert dead_letters[0].job_id == job.id


# Category 11 - time/timezone: storage stays naive UTC and rendering tags UTC.
def test_time_values_are_utc_normalized() -> None:
    assert utcnow_naive().tzinfo is None
    assert to_iso(datetime(2026, 3, 8, 1, 30)) == "2026-03-08T01:30:00+00:00"
    assert to_iso(datetime(2026, 3, 8, 1, 30, tzinfo=UTC)) == "2026-03-08T01:30:00+00:00"


# Category 12 - encoding/unicode: text survives, secrets are still redacted.
def test_unicode_is_preserved_and_secrets_redacted() -> None:
    cleaned = sanitize_detail({"text": "emoji \U0001f600 中文 RTL \u202e", "password": "hunter2"})
    assert cleaned["text"] == "emoji \U0001f600 中文 RTL \u202e"
    assert cleaned["password"] == "[REDACTED]"


# Category 13 - protocol/contract: unknown fields and invalid enums are rejected.
def test_contract_rejects_unknown_fields_and_invalid_enums() -> None:
    with pytest.raises(ValidationError):
        ProjectCreate.model_validate({"name": "ok", "unexpected": True})
    with pytest.raises(ValidationError):
        EvaluatorMetricIn.model_validate({"name": "accuracy", "direction": "sideways"})


# Category 14 - permissions/tenant: another tenant can neither list nor fetch.
def test_cross_tenant_access_is_hidden() -> None:
    owner = TenantContext(tenant_id="tenant-a", subject_id="qa", scopes=frozenset(), trace_id="edge")
    intruder = TenantContext(tenant_id="tenant-b", subject_id="qa", scopes=frozenset(), trace_id="edge")
    projects = InMemoryProjects()
    project = projects.create_project(owner, name="Tenant A only")

    assert projects.list_projects(intruder, cursor=None, limit=10).items == []
    with pytest.raises(NotFoundError):
        projects.get_project(intruder, project.id)


# The registry makes coverage auditable instead of implied by test names.
CATEGORY_TESTS: dict[int, tuple[str, Callable[..., None]]] = {
    1: ("zero/empty", test_zero_empty_pagination_and_run_creation),
    2: ("singleton/min", test_singleton_minimum_page),
    3: ("limits/overflow", test_limits_and_overflow_are_rejected),
    4: ("duplicate/idempotency", test_duplicate_enqueue_is_idempotent),
    5: ("concurrency/race", test_concurrent_item_claim_has_one_winner),
    6: ("partial failure", test_partial_failure_keeps_completed_items),
    7: ("timeout/cancel", test_timeout_is_recorded_per_item),
    8: ("dependency failure", test_dependency_failure_opens_circuit),
    9: ("malicious/adversarial", test_path_traversal_and_injection_are_rejected_or_inert),
    10: ("lifecycle", test_retry_exhaustion_reaches_dead_letter),
    11: ("time/timezone", test_time_values_are_utc_normalized),
    12: ("encoding/unicode", test_unicode_is_preserved_and_secrets_redacted),
    13: ("protocol/contract", test_contract_rejects_unknown_fields_and_invalid_enums),
    14: ("permissions/tenant", test_cross_tenant_access_is_hidden),
}


def test_all_14_edge_categories_are_covered() -> None:
    expected = set(range(1, 15))
    assert set(CATEGORY_TESTS) == expected
    assert all(callable(test) for _, test in CATEGORY_TESTS.values())
    assert all(test.__name__.startswith("test_") for _, test in CATEGORY_TESTS.values())
