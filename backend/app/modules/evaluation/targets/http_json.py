"""Declarative HTTP JSON target adapter.

The adapter is deliberately boring: a transport callable isolates urllib, all
mapping is dot-path based, and the template layer only allows whitelisted
variables. Raw responses can be persisted through ``raw_store`` for replay.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from app.core.context import TenantContext
from app.core.errors import InvalidArgumentError, UpstreamUnavailableError
from app.modules.evaluation.targets.config import TargetConfig, render_template, validate_target_config
from app.modules.evaluation.types import AgentRequest, AgentResponse

_DEFAULT_RESPONSE_MAP = {
    "output": "output",
    "trace_id": "trace_id",
    "usage": "usage",
    "finish_reason": "finish_reason",
}


@dataclass(frozen=True)
class HttpRequest:
    method: str
    url: str
    headers: dict[str, str]
    body: bytes
    timeout_seconds: float


@dataclass(frozen=True)
class HttpResponse:
    status: int
    body: bytes
    headers: dict[str, str] = field(default_factory=dict)


HttpTransport = Callable[[HttpRequest], HttpResponse]
RawStore = Callable[[str, bytes], str]
SecretResolver = Callable[[str], str]


def _urllib_transport(request: HttpRequest) -> HttpResponse:
    http_request = urllib.request.Request(
        request.url,
        data=request.body,
        headers=request.headers,
        method=request.method,
    )
    try:
        with urllib.request.urlopen(http_request, timeout=request.timeout_seconds) as response:
            return HttpResponse(status=int(response.status), body=response.read(), headers=dict(response.headers))
    except urllib.error.HTTPError as exc:
        return HttpResponse(status=int(exc.code), body=exc.read(), headers=dict(exc.headers or {}))
    except (urllib.error.URLError, TimeoutError) as exc:
        raise UpstreamUnavailableError("target request failed") from exc


def _extract(path: str, data: Any) -> Any:
    if not path:
        return data
    current = data
    for part in path.split("."):
        if isinstance(current, dict):
            current = current.get(part)
        elif isinstance(current, list):
            try:
                current = current[int(part)]
            except (ValueError, IndexError):
                return None
        else:
            return None
        if current is None:
            return None
    return current


class HttpJsonAdapter:
    def __init__(
        self,
        config: TargetConfig | dict[str, Any],
        *,
        transport: HttpTransport | None = None,
        raw_store: RawStore | None = None,
        secret_resolver: SecretResolver | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._config = validate_target_config(config) if isinstance(config, dict) else config
        self._transport = transport or _urllib_transport
        self._raw_store = raw_store
        self._secret_resolver = secret_resolver
        self._sleep = sleep

    @property
    def config(self) -> TargetConfig:
        return self._config

    def build_payload(self, request: AgentRequest, variables: dict[str, Any]) -> Any:
        if self._config.body is not None:
            return render_template(self._config.body, variables)
        return {"input": variables["input"]}

    def response_mapping(self) -> dict[str, str]:
        return {**_DEFAULT_RESPONSE_MAP, **self._config.response}

    def build_request(self, ctx: TenantContext, request: AgentRequest) -> HttpRequest:
        variables = {
            "sample_key": request.sample_key,
            "input": request.payload.get("input", request.payload.get("prompt", request.payload)),
            "expected": request.expected if request.expected is not None else request.payload.get("expected", ""),
            "trace_id": request.trace_id or "",
        }
        headers = {str(key): str(value) for key, value in render_template(self._config.headers, variables).items()}
        headers.setdefault("Content-Type", "application/json")
        if self._config.auth_ref and self._secret_resolver is not None:
            headers.setdefault("Authorization", f"Bearer {self._secret_resolver(self._config.auth_ref)}")
        payload = self.build_payload(request, variables)
        body = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        url = str(render_template(self._config.url, variables))
        return HttpRequest(
            method=self._config.method,
            url=url,
            headers=headers,
            body=body,
            timeout_seconds=self._config.timeout_seconds,
        )

    def invoke(self, ctx: TenantContext, request: AgentRequest) -> AgentResponse:
        http_request = self.build_request(ctx, request)
        response: HttpResponse | None = None
        last_error: Exception | None = None
        for attempt in range(self._config.max_retries + 1):
            try:
                response = self._transport(http_request)
            except UpstreamUnavailableError as exc:
                last_error = exc
                if attempt >= self._config.max_retries:
                    raise
                self._sleep(min(0.2 * (2**attempt), 2.0))
                continue
            if response.status in self._config.retry_statuses and attempt < self._config.max_retries:
                self._sleep(min(0.2 * (2**attempt), 2.0))
                continue
            break
        if response is None:
            raise UpstreamUnavailableError("target request failed") from last_error
        if response.status in self._config.retry_statuses:
            raise UpstreamUnavailableError(f"target returned a retryable error ({response.status})")
        if 400 <= response.status < 500:
            raise InvalidArgumentError("target rejected the request", status=response.status)
        if response.status >= 500:
            raise UpstreamUnavailableError(f"target returned a server error ({response.status})")

        raw_ref = None
        if self._raw_store is not None:
            key = f"{ctx.tenant_id}/{request.sample_key}"
            raw_ref = self._raw_store(key, response.body)
        else:
            raw_ref = f"artifact://evaluation/{ctx.tenant_id}/{request.sample_key}.json"
        try:
            data: Any = json.loads(response.body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise InvalidArgumentError("target response is not valid JSON") from exc
        mapping = self.response_mapping()
        output = _extract(mapping["output"], data)
        if output is None:
            if isinstance(data, str):
                output = data
            else:
                raise InvalidArgumentError("target response did not contain the configured output field")
        usage_raw = _extract(mapping.get("usage", ""), data) if mapping.get("usage") else None
        usage = (
            {str(key): int(value) for key, value in usage_raw.items() if isinstance(value, (int, float))}
            if isinstance(usage_raw, dict)
            else {}
        )
        mapped_raw_ref = _extract(mapping.get("raw_ref", ""), data) if mapping.get("raw_ref") else None
        trace_id = _extract(mapping.get("trace_id", ""), data) if mapping.get("trace_id") else None
        finish_reason = _extract(mapping.get("finish_reason", ""), data) if mapping.get("finish_reason") else None
        return AgentResponse(
            output=output if isinstance(output, str) else json.dumps(output, ensure_ascii=False, sort_keys=True),
            trace_id=str(trace_id) if trace_id is not None else request.trace_id,
            usage=usage,
            cost_usd=0.0,
            raw_ref=str(mapped_raw_ref or raw_ref),
            finish_reason=str(finish_reason) if finish_reason is not None else None,
            raw=data,
        )
