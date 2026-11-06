"""Target SPI, config schema, template whitelist and declarative adapters (EVL-13/14)."""

from __future__ import annotations

import json

import pytest

from app.core.context import TenantContext
from app.core.errors import InvalidArgumentError, UpstreamUnavailableError
from app.modules.evaluation.targets.config import render_template, validate_target_config
from app.modules.evaluation.targets.http_json import HttpJsonAdapter, HttpRequest, HttpResponse
from app.modules.evaluation.targets.openai_compat import OpenAICompatibleAdapter
from app.modules.evaluation.targets.registry import TargetRegistry
from app.modules.evaluation.targets.trace import StaticTraceSource
from app.modules.evaluation.types import AgentRequest, TraceSpan

_CTX = TenantContext(tenant_id="tenant-a", subject_id="user:1")


def _config(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "adapter": "http_json",
        "config_version": "cfg-1",
        "adapter_version": "v2",
        "protocol": "http",
        "url": "https://example.test/invoke",
        "method": "POST",
        "headers": {"X-Test": "1"},
        "body": {"input": "{{input}}", "sample": "{{sample_key}}"},
        "response": {"output": "result.text", "trace_id": "result.trace", "usage": "usage"},
        "timeout_seconds": 5,
        "max_retries": 1,
    }
    values.update(overrides)
    return values


def test_config_schema_validation() -> None:
    config = validate_target_config(_config())
    assert config.adapter == "http_json"
    assert config.adapter_version == "v2"
    assert config.version == "cfg-1"
    with pytest.raises(InvalidArgumentError):
        validate_target_config(_config(config_version=""))
    with pytest.raises(InvalidArgumentError):
        validate_target_config(_config(unknown_field=True))
    with pytest.raises(InvalidArgumentError):
        validate_target_config(_config(protocol="grpc"))
    with pytest.raises(InvalidArgumentError):
        validate_target_config(_config(auth_ref="plain-token"))


def test_config_rejects_plaintext_secrets() -> None:
    with pytest.raises(InvalidArgumentError):
        validate_target_config(_config(headers={"Authorization": "Bearer abc"}))
    config = validate_target_config(_config(headers={"Authorization": "secret://tenant/key"}))
    assert config.headers["Authorization"].startswith("secret://")


def test_template_whitelist_and_object_placeholder() -> None:
    variables = {"sample_key": "s1", "input": {"question": "2+2?"}, "expected": "4", "trace_id": "t"}
    rendered = render_template({"input": "{{input}}", "name": "{{ sample_key }}"}, variables)
    assert rendered == {"input": {"question": "2+2?"}, "name": "s1"}
    with pytest.raises(InvalidArgumentError):
        render_template({"input": "{{__import__}}"}, variables)
    with pytest.raises(InvalidArgumentError):
        render_template("{{ missing }}", variables)


def test_registry_register_create_and_duplicate() -> None:
    class Dummy:
        def __init__(self, config: object) -> None:
            self.config = config

        def invoke(self, ctx: TenantContext, request: AgentRequest):  # pragma: no cover - contract only
            raise NotImplementedError

    registry = TargetRegistry()
    registry.register("dummy", Dummy)
    assert registry.names() == ["dummy"]
    adapter = registry.create("dummy", {"adapter": "dummy", "config_version": "1"})
    assert isinstance(adapter, Dummy)
    with pytest.raises(InvalidArgumentError):
        registry.register("dummy", Dummy)
    with pytest.raises(InvalidArgumentError):
        registry.get("missing")


def test_http_adapter_maps_request_and_response() -> None:
    requests: list[HttpRequest] = []
    stored: dict[str, bytes] = {}

    def raw_store(key: str, body: bytes) -> str:
        stored[key] = body
        return key

    def transport(request: HttpRequest) -> HttpResponse:
        requests.append(request)
        return HttpResponse(
            status=200,
            body=json.dumps(
                {
                    "result": {"text": "hello", "trace": "trace-1"},
                    "usage": {"prompt_tokens": 3, "completion_tokens": 2},
                }
            ).encode(),
        )

    adapter = HttpJsonAdapter(
        _config(),
        transport=transport,
        raw_store=raw_store,
        sleep=lambda _seconds: None,
    )
    response = adapter.invoke(_CTX, AgentRequest("s1", {"input": "hi"}, trace_id="trace-in"))
    assert response.output == "hello"
    assert response.trace_id == "trace-1"
    assert response.usage == {"prompt_tokens": 3, "completion_tokens": 2}
    assert response.raw_ref.startswith("tenant-a/s1")
    assert requests[0].method == "POST"
    assert requests[0].headers["X-Test"] == "1"
    payload = json.loads(requests[0].body)
    assert payload == {"input": "hi", "sample": "s1"}


def test_http_adapter_retries_retryable_status() -> None:
    calls: list[int] = []

    def transport(request: HttpRequest) -> HttpResponse:
        calls.append(1)
        if len(calls) == 1:
            return HttpResponse(status=503, body=b"{}")
        return HttpResponse(status=200, body=b'{"output": "ok"}')

    adapter = HttpJsonAdapter(
        _config(max_retries=1, response={"output": "output"}),
        transport=transport,
        sleep=lambda _seconds: None,
    )
    assert adapter.invoke(_CTX, AgentRequest("s1", {"input": "hi"})).output == "ok"
    assert len(calls) == 2

    def unavailable(request: HttpRequest) -> HttpResponse:
        return HttpResponse(status=503, body=b"{}")

    failing = HttpJsonAdapter(_config(max_retries=0), transport=unavailable)
    with pytest.raises(UpstreamUnavailableError):
        failing.invoke(_CTX, AgentRequest("s1", {"input": "hi"}))

    def bad_request(request: HttpRequest) -> HttpResponse:
        return HttpResponse(status=400, body=b"{}")

    rejected = HttpJsonAdapter(_config(max_retries=0), transport=bad_request)
    with pytest.raises(InvalidArgumentError):
        rejected.invoke(_CTX, AgentRequest("s1", {"input": "hi"}))


def test_openai_compatible_adapter_request_shape() -> None:
    captured: list[HttpRequest] = []

    def transport(request: HttpRequest) -> HttpResponse:
        captured.append(request)
        return HttpResponse(
            status=200,
            body=json.dumps(
                {
                    "id": "chat-1",
                    "choices": [{"message": {"content": "answer"}, "finish_reason": "stop"}],
                    "usage": {"prompt_tokens": 4, "completion_tokens": 1},
                }
            ).encode(),
        )

    adapter = OpenAICompatibleAdapter(
        {
            "adapter": "openai_compat",
            "config_version": "cfg-1",
            "protocol": "openai",
            "url": "https://example.test/v1",
            "model": "model-x",
            "system_prompt": "Be concise",
        },
        transport=transport,
    )
    response = adapter.invoke(_CTX, AgentRequest("s1", {"input": "question"}))
    assert response.output == "answer"
    assert response.finish_reason == "stop"
    body = json.loads(captured[0].body)
    assert captured[0].url == "https://example.test/v1/chat/completions"
    assert body["model"] == "model-x"
    assert body["messages"][0] == {"role": "system", "content": "Be concise"}
    assert body["messages"][1]["content"] == "question"


def test_static_trace_source_contract() -> None:
    source = StaticTraceSource(
        {
            "trace-1": {
                "spans": [
                    {
                        "trace_id": "trace-1",
                        "span_id": "s1",
                        "name": "invoke",
                        "start_time_unix_nano": 1_000_000_000,
                        "end_time_unix_nano": 1_500_000_000,
                    }
                ]
            }
        }
    )
    spans = source.fetch(_CTX, "trace-1")
    assert isinstance(spans[0], TraceSpan)
    assert spans[0].name == "invoke"
