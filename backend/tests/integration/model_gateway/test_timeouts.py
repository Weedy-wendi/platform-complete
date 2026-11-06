"""Three-layer timeout tests (MGW-07)."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, select

from app.core.context import TenantContext
from app.core.db import Base, make_session_factory
from app.core.errors import InvalidArgumentError
from app.modules.model_gateway.models import ModelCall, ProviderConfig
from app.modules.model_gateway.public_types import ModelRequest, ProviderResult
from app.modules.model_gateway.service import ModelGatewayService

_TABLES = [ProviderConfig.__table__, ModelCall.__table__]


class CapturingCompletion:
    def __init__(self) -> None:
        self.requests: list[ModelRequest] = []

    def __call__(self, config, request):
        self.requests.append(request)
        return ProviderResult(text="ok")


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
    return TenantContext(tenant_id="tenant-a", subject_id="judge", trace_id="trace-1")


def _create(service: ModelGatewayService, ctx: TenantContext, **overrides):
    values = {
        "name": "judge",
        "provider": "openai",
        "model": "gpt-4o-mini",
        "secret_ref": "secret://tenant-a/openai",
        "max_retries": 1,
        "input_cost_per_million": 0.0,
        "output_cost_per_million": 0.0,
        "enabled": True,
    }
    values.update(overrides)
    return service.create_provider(ctx, **values)


def test_valid_timeout_ordering_is_accepted(factory, ctx) -> None:
    service = ModelGatewayService(factory, CapturingCompletion(), sleep=lambda _: None)
    provider = _create(
        service,
        ctx,
        connect_timeout_seconds=2.0,
        read_timeout_seconds=10.0,
        timeout_seconds=20.0,
    )

    with factory() as session:
        row = session.get(ProviderConfig, provider.id)
        assert row is not None
        assert row.connect_timeout_seconds == 2.0
        assert row.read_timeout_seconds == 10.0
        assert row.timeout_seconds == 20.0


@pytest.mark.parametrize(
    ("connect", "read", "total"),
    [
        (10.0, 5.0, 20.0),
        (2.0, 30.0, 20.0),
        (0.0, 5.0, 20.0),
        (2.0, -1.0, 20.0),
    ],
)
def test_invalid_timeout_ordering_is_rejected(factory, ctx, connect, read, total) -> None:
    service = ModelGatewayService(factory, CapturingCompletion(), sleep=lambda _: None)
    with pytest.raises(InvalidArgumentError):
        _create(
            service,
            ctx,
            connect_timeout_seconds=connect,
            read_timeout_seconds=read,
            timeout_seconds=total,
        )


def test_completion_receives_configured_timeouts(factory, ctx) -> None:
    completion = CapturingCompletion()
    service = ModelGatewayService(factory, completion, sleep=lambda _: None)
    _create(
        service,
        ctx,
        connect_timeout_seconds=2.0,
        read_timeout_seconds=10.0,
        timeout_seconds=20.0,
    )
    request = ModelRequest(provider="judge", model="gpt-4o-mini", messages=[])

    service.complete(ctx, request)

    assert len(completion.requests) == 1
    sent = completion.requests[0]
    assert sent.connect_timeout_seconds == 2.0
    assert sent.read_timeout_seconds == 10.0
    assert sent.timeout_seconds == 20.0


def test_request_overrides_are_forwarded(factory, ctx) -> None:
    completion = CapturingCompletion()
    service = ModelGatewayService(factory, completion, sleep=lambda _: None)
    _create(service, ctx)
    request = ModelRequest(
        provider="judge",
        model="gpt-4o-mini",
        messages=[],
        connect_timeout_seconds=1.0,
        read_timeout_seconds=5.0,
        timeout_seconds=10.0,
    )

    service.complete(ctx, request)

    sent = completion.requests[0]
    assert sent.connect_timeout_seconds == 1.0
    assert sent.read_timeout_seconds == 5.0
    assert sent.timeout_seconds == 10.0


def test_invalid_request_ordering_is_rejected(factory, ctx) -> None:
    service = ModelGatewayService(factory, CapturingCompletion(), sleep=lambda _: None)
    _create(service, ctx)
    request = ModelRequest(
        provider="judge",
        model="gpt-4o-mini",
        messages=[],
        connect_timeout_seconds=10.0,
        read_timeout_seconds=5.0,
        timeout_seconds=20.0,
    )

    with pytest.raises(InvalidArgumentError):
        service.complete(ctx, request)
    with factory() as session:
        assert session.scalar(select(ModelCall)) is None
