"""14-class edge-case matrix (QUAL-05).

The matrix intentionally stays in-process (SQLite/fakes) so it can run in CI
without external services and stay well below the 10-minute budget.
"""

from __future__ import annotations

import contextvars
from datetime import timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.clock import utcnow_naive
from app.core.context import TenantContext, get_tenant_context
from app.core.db import Base, make_session_factory
from app.core.errors import (
    InvalidArgumentError,
    InvalidCursorError,
    TenantRequiredError,
    UnauthorizedError,
    UpstreamUnavailableError,
)
from app.core.repository import TenantScopedRepository
from app.modules.assets.models import Artifact
from app.modules.assets.service import ArtifactService
from app.modules.assets.storage import build_key
from app.modules.audit.models import AuditLog
from app.modules.audit.reader import SqlAuditReader
from app.modules.identity.api_key import ApiKeyService, InMemoryApiKeyStore
from app.modules.identity.models import Tenant
from app.modules.identity.tenant_status import SqlTenantStatusChecker
from app.modules.jobs.models import DeadLetterTask, IdempotencyKey, Job, JobEvent
from app.modules.jobs.public_types import JobSpec
from app.modules.jobs.service import JobService
from app.modules.model_gateway.models import ModelCall, ProviderConfig
from app.modules.model_gateway.policy import CircuitBreaker
from app.modules.model_gateway.public_types import ModelRequest
from app.modules.model_gateway.service import ModelGatewayService, ProviderError
from tests.support.core_models import Widget
from tests.support.storage import FakeStorage

_TABLES = [
    Widget.__table__,
    AuditLog.__table__,
    Tenant.__table__,
    Job.__table__,
    JobEvent.__table__,
    DeadLetterTask.__table__,
    IdempotencyKey.__table__,
    Artifact.__table__,
    ProviderConfig.__table__,
    ModelCall.__table__,
]


@pytest.fixture()
def factory():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine, tables=_TABLES)
    try:
        yield make_session_factory(engine), engine
    finally:
        engine.dispose()


@pytest.fixture()
def ctx() -> TenantContext:
    return TenantContext(tenant_id="tenant-a", subject_id="qa", scopes=frozenset(), trace_id="trace")


def test_missing_tenant_context() -> None:
    def run() -> None:
        with pytest.raises(TenantRequiredError):
            get_tenant_context()

    contextvars.Context().run(run)


def test_cross_tenant_repository(factory) -> None:
    _, engine = factory
    with Session(engine) as session:
        session.add_all([Widget(tenant_id="tenant-a", name="a"), Widget(tenant_id="tenant-b", name="b")])
        session.commit()
        assert [row.name for row in TenantScopedRepository(session, "tenant-a").list(Widget)] == ["a"]


def test_invalid_cursor(factory, ctx) -> None:
    factory_, _ = factory
    with pytest.raises(InvalidCursorError):
        SqlAuditReader(factory_).query(ctx, cursor="bad")


def test_duplicate_job_enqueue(factory, ctx) -> None:
    service = JobService(factory[0])
    spec = JobSpec("evaluation.run", {}, "edge-key")
    assert service.enqueue(ctx, spec).id == service.enqueue(ctx, spec).id


def test_illegal_job_transition(factory, ctx) -> None:
    service = JobService(factory[0])
    job = service.enqueue(ctx, JobSpec("evaluation.run", {}, "edge-transition"))
    with pytest.raises(InvalidArgumentError):
        service.succeed(ctx, job.id)


def test_retry_exhaustion_dlq(factory, ctx) -> None:
    service = JobService(factory[0])
    job = service.enqueue(ctx, JobSpec("evaluation.run", {}, "edge-dlq"))
    for _ in range(3):
        service.start(ctx, job.id)
        service.fail(ctx, job.id, "boom", retryable=True)
    assert len(service.dead_letters(ctx)) == 1


def test_stale_job_recovery(factory, ctx) -> None:
    service = JobService(factory[0])
    job = service.enqueue(ctx, JobSpec("evaluation.run", {}, "edge-stale"))
    service.start(ctx, job.id)
    with factory[0]() as session:
        row = session.get(Job, job.id)
        assert row is not None
        row.updated_at = utcnow_naive() - timedelta(hours=2)
        session.commit()
    assert service.recover_stale(ctx, older_than_seconds=3600) == 1


def test_disabled_tenant(factory) -> None:
    factory_, _ = factory
    with factory_() as session:
        session.add(Tenant(id="tenant-a", name="A", slug="a", status="disabled", created_by="qa", updated_by="qa"))
        session.commit()
    assert SqlTenantStatusChecker(factory_).is_active("tenant-a") is False


def test_revoked_api_key() -> None:
    service = ApiKeyService(InMemoryApiKeyStore(), pepper="pepper")
    issued = service.issue(tenant_id="tenant-a", name="k", scopes={"mcp:projects:read"})
    service.revoke(issued.key_id)
    with pytest.raises(UnauthorizedError):
        service.verify(issued.raw_key)


def test_malformed_api_key() -> None:
    service = ApiKeyService(InMemoryApiKeyStore(), pepper="pepper")
    with pytest.raises(UnauthorizedError):
        service.verify("not-a-key")


def test_artifact_key_traversal() -> None:
    with pytest.raises(InvalidArgumentError):
        build_key(tenant_id="t", asset_type="a", asset_id="b", version="v", filename="../x")


def test_artifact_checksum_mismatch(factory, ctx) -> None:
    storage = FakeStorage()
    service = ArtifactService(storage, factory[0])
    key = build_key(tenant_id="tenant-a", asset_type="dataset", asset_id="d", version="v1", filename="a.csv")
    ref = service.create(ctx, key=key, data=b"abc", mime_type="text/csv")
    storage.tamper_reads = True
    with pytest.raises(InvalidArgumentError):
        service.get_bytes(ctx, ref.artifact_id)


def test_gateway_4xx_not_retried(factory, ctx) -> None:
    calls = 0

    def completion(config, request):
        nonlocal calls
        calls += 1
        raise ProviderError("bad", status_code=400)

    service = ModelGatewayService(factory[0], completion, sleep=lambda _: None)
    service.create_provider(
        ctx,
        name="p",
        provider="openai",
        model="m",
        secret_ref="secret://x",
        timeout_seconds=1,
        max_retries=3,
        input_cost_per_million=0,
        output_cost_per_million=0,
        enabled=True,
    )
    with pytest.raises(InvalidArgumentError):
        service.complete(ctx, ModelRequest(provider="p", model="m", messages=[]))
    assert calls == 1


def test_circuit_breaker_open() -> None:
    breaker = CircuitBreaker(failure_threshold=1, recovery_seconds=10, clock=lambda: 0)
    breaker.before_call()
    breaker.record_failure()
    with pytest.raises(UpstreamUnavailableError):
        breaker.before_call()
