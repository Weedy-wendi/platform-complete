"""Model gateway: provider CRUD, LiteLLM adapter, retries, cost accounting."""

from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from dataclasses import dataclass, replace
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.core.clock import utcnow_naive
from app.core.context import TenantContext
from app.core.errors import (
    InvalidArgumentError,
    NotFoundError,
    ServiceUnavailableError,
    UpstreamUnavailableError,
)
from app.core.ids import new_ulid
from app.core.kill_switch import KILL_SWITCHES
from app.core.logging import get_logger
from app.core.repository import TenantScopedRepository
from app.core.secrets import DEFAULT_SECRET_RESOLVER, SecretResolver, should_resolve
from app.modules.model_gateway.models import ModelCall, ProviderConfig
from app.modules.model_gateway.policy import CircuitBreaker, RetryPolicy
from app.modules.model_gateway.public_types import (
    ModelRequest,
    ModelResponse,
    ProviderCompletion,
    ProviderResult,
    RawStore,
)

_logger = get_logger(__name__)

_DEFAULT_TOTAL_TIMEOUT = 30.0
_DEFAULT_CONNECT_TIMEOUT = 5.0
_DEFAULT_READ_TIMEOUT = 30.0


def _validate_timeouts(connect: float, read: float, total: float) -> None:
    for name, value in (
        ("connect_timeout_seconds", connect),
        ("read_timeout_seconds", read),
        ("timeout_seconds", total),
    ):
        if value <= 0:
            raise InvalidArgumentError("timeouts must be positive", timeout=name, value=value)
    if not connect <= read <= total:
        raise InvalidArgumentError(
            "timeouts must satisfy connect <= read <= total",
            connect_timeout_seconds=connect,
            read_timeout_seconds=read,
            timeout_seconds=total,
        )


def _provider_timeouts(values: dict[str, Any]) -> tuple[float, float, float]:
    """Resolve provider timeout defaults and validate their ordering."""

    total = values.get("timeout_seconds")
    total_value = _DEFAULT_TOTAL_TIMEOUT if total is None else float(total)
    connect = values.get("connect_timeout_seconds")
    connect_value = min(_DEFAULT_CONNECT_TIMEOUT, total_value) if connect is None else float(connect)
    read = values.get("read_timeout_seconds")
    read_value = min(_DEFAULT_READ_TIMEOUT, total_value) if read is None else float(read)
    _validate_timeouts(connect_value, read_value, total_value)
    return connect_value, read_value, total_value


def _normalized_request(config: ProviderConfig, request: ModelRequest) -> ModelRequest:
    """Merge request overrides with provider defaults and validate ordering."""

    total = float(request.timeout_seconds)
    total_explicit = total != _DEFAULT_TOTAL_TIMEOUT
    if not total_explicit:
        total = float(getattr(config, "timeout_seconds", total) or total)

    connect = float(request.connect_timeout_seconds)
    connect_explicit = connect != _DEFAULT_CONNECT_TIMEOUT
    if not connect_explicit:
        connect = float(getattr(config, "connect_timeout_seconds", connect) or connect)

    read = float(request.read_timeout_seconds)
    read_explicit = read != _DEFAULT_READ_TIMEOUT
    if not read_explicit:
        read = float(getattr(config, "read_timeout_seconds", read) or read)

    # Keep older rows (or a caller lowering only the total) usable without
    # weakening validation for explicitly configured values.
    if not connect_explicit:
        connect = min(connect, read, total)
    if not read_explicit:
        read = min(read, total)
    _validate_timeouts(connect, read, total)
    return replace(
        request,
        timeout_seconds=total,
        connect_timeout_seconds=connect,
        read_timeout_seconds=read,
    )


def _completion_timeout(request: ModelRequest) -> Any:
    try:
        import httpx
    except ImportError:  # pragma: no cover - httpx ships with the dev extras
        return request.timeout_seconds
    return httpx.Timeout(
        request.timeout_seconds,
        connect=request.connect_timeout_seconds,
        read=request.read_timeout_seconds,
    )


class ProviderError(Exception):
    def __init__(self, message: str, *, status_code: int | None = None, retry_after: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.retry_after = retry_after


@dataclass(frozen=True)
class ProviderView:
    id: str
    tenant_id: str
    name: str
    provider: str
    model: str
    secret_ref: str
    enabled: bool


def compute_cost(config: ProviderConfig, usage: dict[str, int]) -> float:
    prompt = int(usage.get("prompt_tokens", 0))
    completion = int(usage.get("completion_tokens", 0))
    return prompt * config.input_cost_per_million / 1_000_000 + completion * config.output_cost_per_million / 1_000_000


def litellm_completion(config: Any, request: ModelRequest) -> ProviderResult:
    try:
        import litellm
    except ImportError as exc:
        raise ServiceUnavailableError("litellm is required for the default provider") from exc

    response = litellm.completion(
        model=f"{config.provider}/{config.model}",
        messages=request.messages,
        temperature=request.temperature,
        seed=request.seed,
        max_tokens=request.max_tokens,
        timeout=_completion_timeout(request),
    )
    choice = response["choices"][0]
    text = choice["message"]["content"]
    usage = response.get("usage", {})
    return ProviderResult(
        text=text,
        usage={
            "prompt_tokens": int(usage.get("prompt_tokens", 0)),
            "completion_tokens": int(usage.get("completion_tokens", 0)),
        },
        finish_reason=choice.get("finish_reason"),
        raw=response,
    )


class ModelGatewayService:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        completion: ProviderCompletion | None = None,
        *,
        retry_policy: RetryPolicy | None = None,
        circuit_factory: Any = CircuitBreaker,
        sleep: Any = time.sleep,
        raw_store: RawStore | None = None,
        secret_resolver: SecretResolver | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._completion = completion or litellm_completion
        self._retry = retry_policy or RetryPolicy()
        self._circuits: dict[str, Any] = {}
        self._circuit_factory = circuit_factory
        self._sleep = sleep
        self._raw_store = raw_store
        self._secret_resolver = secret_resolver or DEFAULT_SECRET_RESOLVER

    # Provider config -------------------------------------------------------

    def create_provider(self, ctx: TenantContext, **values: Any) -> ProviderView:
        secret_ref = str(values.get("secret_ref") or "")
        if not secret_ref.startswith("secret://"):
            raise InvalidArgumentError("secret_ref must use the secret:// scheme")
        connect, read, total = _provider_timeouts(values)
        values.update(
            connect_timeout_seconds=connect,
            read_timeout_seconds=read,
            timeout_seconds=total,
        )
        with self._session_factory() as session:
            exists = session.scalar(
                select(ProviderConfig).where(
                    ProviderConfig.tenant_id == ctx.tenant_id,
                    ProviderConfig.name == values.get("name"),
                )
            )
            if exists is not None:
                raise InvalidArgumentError("provider already exists", name=values.get("name"))
            config = ProviderConfig(id=new_ulid(), tenant_id=ctx.tenant_id, **values)
            session.add(config)
            session.commit()
            return _provider_view(config)

    def set_enabled(self, ctx: TenantContext, provider_id: str, enabled: bool) -> ProviderView:
        with self._session_factory() as session:
            config = TenantScopedRepository(session, ctx.tenant_id).get(ProviderConfig, provider_id)
            if config is None:
                raise NotFoundError("Provider not found")
            config.enabled = enabled
            session.commit()
            return _provider_view(config)

    def list_providers(self, ctx: TenantContext) -> list[ProviderView]:
        with self._session_factory() as session:
            rows = session.scalars(select(ProviderConfig).where(ProviderConfig.tenant_id == ctx.tenant_id))
            return [_provider_view(row) for row in rows]

    # Calls -----------------------------------------------------------------

    def complete(self, ctx: TenantContext, request: ModelRequest) -> ModelResponse:
        KILL_SWITCHES.require("models")
        with self._session_factory() as session:
            config = session.scalar(
                select(ProviderConfig).where(
                    ProviderConfig.tenant_id == ctx.tenant_id,
                    ProviderConfig.name == request.provider,
                    ProviderConfig.model == request.model,
                )
            )
            if config is None:
                raise NotFoundError("Provider not found")
            if not config.enabled:
                raise InvalidArgumentError("Provider is disabled")
            session.expunge(config)

        request = _normalized_request(config, request)
        if should_resolve(config.secret_ref):
            request = replace(request, secret=self._secret_resolver.resolve(config.secret_ref))
        circuit = self._circuit(f"{config.provider}:{config.model}")
        last_error: Exception | None = None
        for attempt in range(config.max_retries):
            try:
                circuit.before_call()
                started = time.perf_counter()
                result = self._call_with_timeout(config, request)
                latency_ms = int((time.perf_counter() - started) * 1000)
                cost = compute_cost(config, result.usage)
                circuit.record_success()
                call_id = new_ulid()
                raw_ref = getattr(result, "raw_ref", None)
                if raw_ref is None:
                    raw_ref = self._persist_raw(ctx, call_id, config, request, result)
                self._record(
                    ctx,
                    config,
                    status="succeeded",
                    usage=result.usage,
                    cost=cost,
                    latency_ms=latency_ms,
                    call_id=call_id,
                    raw_ref=raw_ref,
                )
                return ModelResponse(
                    text=result.text,
                    usage=result.usage,
                    cost_usd=cost,
                    raw_ref=raw_ref,
                    finish_reason=result.finish_reason,
                )
            except Exception as exc:
                last_error = exc
                circuit.record_failure()
                if not _retryable(exc) or attempt + 1 >= config.max_retries:
                    self._record(
                        ctx,
                        config,
                        status="failed",
                        usage={},
                        cost=0.0,
                        latency_ms=0,
                        error_code=_error_code(exc),
                    )
                    raise _map_error(exc) from exc
                self._sleep(self._retry.delay(attempt))

        raise _map_error(last_error) if last_error is not None else UpstreamUnavailableError()

    def _call_with_timeout(self, config: ProviderConfig, request: ModelRequest) -> ProviderResult:
        timeout = request.timeout_seconds or config.timeout_seconds
        executor = ThreadPoolExecutor(max_workers=1)
        future = executor.submit(self._completion, config, request)
        try:
            return future.result(timeout=timeout)
        except FutureTimeoutError as exc:
            future.cancel()
            raise ProviderError("provider call timed out", status_code=504) from exc
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

    def _circuit(self, key: str) -> Any:
        if key not in self._circuits:
            self._circuits[key] = self._circuit_factory()
        return self._circuits[key]

    def _persist_raw(
        self,
        ctx: TenantContext,
        call_id: str,
        config: ProviderConfig,
        request: ModelRequest,
        result: ProviderResult,
    ) -> str | None:
        """Persist the raw provider exchange; failures never fail the call."""

        if self._raw_store is None:
            return None
        payload = {
            "provider": config.provider,
            "model": config.model,
            "request": {
                "messages": request.messages,
                "temperature": request.temperature,
                "seed": request.seed,
                "max_tokens": request.max_tokens,
            },
            "response": {
                "text": result.text,
                "usage": result.usage,
                "finish_reason": result.finish_reason,
                "raw": result.raw,
            },
        }
        try:
            encoded = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
            return self._raw_store.put_raw(ctx.tenant_id, call_id, encoded)
        except Exception:  # noqa: BLE001 - raw capture is best effort
            _logger.warning("failed to persist raw model response", exc_info=True, extra={"call_id": call_id})
            return None

    def _record(
        self,
        ctx: TenantContext,
        config: ProviderConfig,
        *,
        status: str,
        usage: dict[str, int],
        cost: float,
        latency_ms: int,
        call_id: str | None = None,
        raw_ref: str | None = None,
        error_code: str | None = None,
    ) -> None:
        with self._session_factory() as session:
            session.add(
                ModelCall(
                    id=call_id or new_ulid(),
                    tenant_id=ctx.tenant_id,
                    provider_config_id=config.id,
                    provider=config.provider,
                    model=config.model,
                    status=status,
                    prompt_tokens=int(usage.get("prompt_tokens", 0)),
                    completion_tokens=int(usage.get("completion_tokens", 0)),
                    cost_usd=cost,
                    latency_ms=latency_ms,
                    trace_id=ctx.trace_id,
                    raw_ref=raw_ref,
                    error_code=error_code,
                    created_at=utcnow_naive(),
                )
            )
            session.commit()


def _provider_view(row: ProviderConfig) -> ProviderView:
    return ProviderView(
        id=row.id,
        tenant_id=row.tenant_id,
        name=row.name,
        provider=row.provider,
        model=row.model,
        secret_ref=row.secret_ref,
        enabled=row.enabled,
    )


def _retryable(exc: Exception) -> bool:
    if isinstance(exc, ProviderError):
        return exc.status_code == 429 or (exc.status_code or 0) >= 500
    return isinstance(exc, (UpstreamUnavailableError, TimeoutError))


def _error_code(exc: Exception) -> str:
    if isinstance(exc, ProviderError):
        if exc.status_code == 429:
            return "RATE_LIMITED"
        if exc.status_code and 400 <= exc.status_code < 500:
            return "INVALID_ARGUMENT"
        return "UPSTREAM_UNAVAILABLE"
    return "INTERNAL"


def _map_error(exc: Exception) -> Exception:
    if isinstance(exc, ProviderError):
        if exc.status_code == 429:
            from app.core.errors import RateLimitedError

            return RateLimitedError(exc.retry_after or 1)
        if exc.status_code and 400 <= exc.status_code < 500:
            return InvalidArgumentError(str(exc))
        return UpstreamUnavailableError(str(exc))
    return exc
