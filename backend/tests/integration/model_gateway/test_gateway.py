"""Model gateway tests (MGW-01..05)."""

from __future__ import annotations

import time

import pytest
from sqlalchemy import create_engine, select

from app.core.context import TenantContext
from app.core.db import Base, make_session_factory
from app.core.errors import (
    InvalidArgumentError,
    NotFoundError,
    ServiceUnavailableError,
    UpstreamUnavailableError,
)
from app.core.kill_switch import KILL_SWITCHES
from app.modules.model_gateway.models import ModelCall, ProviderConfig
from app.modules.model_gateway.policy import CircuitBreaker
from app.modules.model_gateway.public_types import ModelRequest, ProviderResult
from app.modules.model_gateway.service import ModelGatewayService, ProviderError

_TABLES = [ProviderConfig.__table__, ModelCall.__table__]


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
    return TenantContext(tenant_id="tenant-a", subject_id="judge", scopes=frozenset(), trace_id="trace-1")


class FakeCompletion:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = 0

    def __call__(self, config, request):
        self.calls += 1
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        if callable(outcome):
            return outcome()
        return outcome


def _provider(service: ModelGatewayService, ctx: TenantContext, **overrides):
    values = {
        "name": "judge",
        "provider": "openai",
        "model": "gpt-4o-mini",
        "secret_ref": "secret://tenant-a/openai",
        "timeout_seconds": 1.0,
        "max_retries": 3,
        "input_cost_per_million": 0.5,
        "output_cost_per_million": 1.5,
        "enabled": True,
    }
    values.update(overrides)
    return service.create_provider(ctx, **values)


def _request() -> ModelRequest:
    return ModelRequest(provider="judge", model="gpt-4o-mini", messages=[{"role": "user", "content": "hi"}])


def test_complete_records_usage_and_cost(factory, ctx) -> None:
    fake = FakeCompletion(
        [
            ProviderResult(
                text="answer", usage={"prompt_tokens": 1000, "completion_tokens": 500}, raw_ref="artifact://r1"
            )
        ]
    )
    service = ModelGatewayService(factory, fake, sleep=lambda _: None)
    _provider(service, ctx)
    response = service.complete(ctx, _request())
    assert response.text == "answer"
    assert response.raw_ref == "artifact://r1"
    assert response.cost_usd == pytest.approx(0.00125)
    with factory() as session:
        row = session.scalar(select(ModelCall))
        assert row is not None
        assert row.status == "succeeded"
        assert row.prompt_tokens == 1000
        assert row.completion_tokens == 500
        assert row.cost_usd == pytest.approx(0.00125)


def test_retry_on_429_then_success(factory, ctx) -> None:
    fake = FakeCompletion(
        [ProviderError("busy", status_code=429, retry_after=1), ProviderResult("ok", {"prompt_tokens": 1})]
    )
    service = ModelGatewayService(factory, fake, sleep=lambda _: None)
    _provider(service, ctx)
    assert service.complete(ctx, _request()).text == "ok"
    assert fake.calls == 2


def test_4xx_is_not_retried(factory, ctx) -> None:
    fake = FakeCompletion([ProviderError("bad request", status_code=400)])
    service = ModelGatewayService(factory, fake, sleep=lambda _: None)
    _provider(service, ctx)
    with pytest.raises(InvalidArgumentError):
        service.complete(ctx, _request())
    assert fake.calls == 1
    with factory() as session:
        assert session.scalar(select(ModelCall)).status == "failed"


def test_total_timeout_fails(factory, ctx) -> None:
    def slow():
        time.sleep(0.2)
        return ProviderResult("late")

    fake = FakeCompletion([slow, slow, slow])
    service = ModelGatewayService(factory, fake, sleep=lambda _: None)
    _provider(service, ctx)
    with pytest.raises(UpstreamUnavailableError):
        service.complete(ctx, ModelRequest(provider="judge", model="gpt-4o-mini", messages=[], timeout_seconds=0.01))


def test_circuit_breaker_opens_and_recovers() -> None:
    now = [0.0]
    breaker = CircuitBreaker(failure_threshold=2, recovery_seconds=10, clock=lambda: now[0])
    breaker.before_call()
    breaker.record_failure()
    breaker.before_call()
    breaker.record_failure()
    assert breaker.state == "open"
    with pytest.raises(UpstreamUnavailableError):
        breaker.before_call()
    now[0] = 11
    breaker.before_call()
    assert breaker.state == "half_open"
    breaker.record_success()
    assert breaker.state == "closed"


def test_disabled_provider_and_cross_tenant(factory, ctx) -> None:
    fake = FakeCompletion([ProviderResult("ok")])
    service = ModelGatewayService(factory, fake, sleep=lambda _: None)
    provider = _provider(service, ctx)
    service.set_enabled(ctx, provider.id, False)
    with pytest.raises(InvalidArgumentError):
        service.complete(ctx, _request())

    other = TenantContext(tenant_id="tenant-b", subject_id="judge", scopes=frozenset(), trace_id="trace-2")
    with pytest.raises(NotFoundError):
        service.complete(other, _request())


def test_secret_ref_must_be_reference(factory, ctx) -> None:
    service = ModelGatewayService(factory, FakeCompletion([]), sleep=lambda _: None)
    with pytest.raises(InvalidArgumentError):
        service.create_provider(
            ctx,
            name="bad",
            provider="openai",
            model="m",
            secret_ref="plain-text",
            timeout_seconds=1.0,
            max_retries=1,
            input_cost_per_million=0.0,
            output_cost_per_million=0.0,
        )


def test_models_kill_switch_blocks_complete(factory, ctx) -> None:
    service = ModelGatewayService(factory, FakeCompletion([]), sleep=lambda _: None)
    _provider(service, ctx)
    KILL_SWITCHES.set("models", True, reason="provider incident")
    try:
        with pytest.raises(ServiceUnavailableError):
            service.complete(ctx, _request())
    finally:
        KILL_SWITCHES.set("models", False)
