"""Raw response capture tests (MGW-06)."""

from __future__ import annotations

import json

import pytest
from sqlalchemy import create_engine, select

from app.core.context import TenantContext
from app.core.db import Base, make_session_factory
from app.modules.model_gateway.models import ModelCall, ProviderConfig
from app.modules.model_gateway.public_types import ModelRequest, ProviderResult
from app.modules.model_gateway.service import ModelGatewayService

_TABLES = [ProviderConfig.__table__, ModelCall.__table__]


class FakeCompletion:
    def __init__(self, result: ProviderResult) -> None:
        self.result = result

    def __call__(self, config, request):
        return self.result


class RecordingRawStore:
    def __init__(self) -> None:
        self.items: list[tuple[str, str, bytes]] = []

    def put_raw(self, tenant_id: str, call_id: str, payload: bytes) -> str:
        self.items.append((tenant_id, call_id, payload))
        return f"artifact://raw/{call_id}"


class FailingRawStore:
    def put_raw(self, tenant_id: str, call_id: str, payload: bytes) -> str:
        raise RuntimeError("artifact store unavailable")


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


def _service(factory, result: ProviderResult, raw_store=None) -> ModelGatewayService:
    return ModelGatewayService(
        factory,
        FakeCompletion(result),
        sleep=lambda _: None,
        raw_store=raw_store,
    )


def _provider(service: ModelGatewayService, ctx: TenantContext) -> None:
    service.create_provider(
        ctx,
        name="judge",
        provider="openai",
        model="gpt-4o-mini",
        secret_ref="secret://tenant-a/openai",
        timeout_seconds=30.0,
        max_retries=1,
        input_cost_per_million=0.5,
        output_cost_per_million=1.5,
        enabled=True,
    )


def _request() -> ModelRequest:
    return ModelRequest(provider="judge", model="gpt-4o-mini", messages=[{"role": "user", "content": "hi"}])


def test_raw_ref_is_populated_when_store_configured(factory, ctx) -> None:
    store = RecordingRawStore()
    result = ProviderResult(text="answer", usage={"prompt_tokens": 3}, raw={"id": "provider-1"})
    service = _service(factory, result, raw_store=store)
    _provider(service, ctx)

    response = service.complete(ctx, _request())

    assert response.raw_ref is not None
    assert response.raw_ref.startswith("artifact://raw/")
    assert len(store.items) == 1
    tenant_id, call_id, payload = store.items[0]
    assert tenant_id == "tenant-a"
    assert response.raw_ref == f"artifact://raw/{call_id}"
    decoded = json.loads(payload)
    assert decoded["provider"] == "openai"
    assert decoded["model"] == "gpt-4o-mini"
    assert decoded["request"]["messages"] == [{"role": "user", "content": "hi"}]
    assert decoded["response"]["text"] == "answer"
    assert decoded["response"]["raw"] == {"id": "provider-1"}

    with factory() as session:
        row = session.scalar(select(ModelCall))
        assert row is not None
        assert row.id == call_id
        assert row.raw_ref == response.raw_ref


def test_provider_supplied_raw_ref_is_not_overwritten(factory, ctx) -> None:
    store = RecordingRawStore()
    result = ProviderResult(text="answer", raw_ref="artifact://provider/raw")
    service = _service(factory, result, raw_store=store)
    _provider(service, ctx)

    response = service.complete(ctx, _request())

    assert response.raw_ref == "artifact://provider/raw"
    assert store.items == []
    with factory() as session:
        row = session.scalar(select(ModelCall))
        assert row is not None
        assert row.raw_ref == "artifact://provider/raw"


def test_raw_store_failure_does_not_fail_the_call(factory, ctx) -> None:
    service = _service(factory, ProviderResult(text="answer"), raw_store=FailingRawStore())
    _provider(service, ctx)

    response = service.complete(ctx, _request())

    assert response.text == "answer"
    assert response.raw_ref is None
    with factory() as session:
        row = session.scalar(select(ModelCall))
        assert row is not None
        assert row.status == "succeeded"
        assert row.raw_ref is None
