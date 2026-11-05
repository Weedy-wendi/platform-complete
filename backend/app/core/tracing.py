"""OpenTelemetry wiring.

The default is a no-op tracer unless an exporter is supplied. Production can
configure an OTLP exporter without touching the MCP adapter.
"""

from __future__ import annotations

import logging
import os

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SpanExporter
from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased

_CONFIGURED = False
_PROVIDER: TracerProvider | None = None
_logger = logging.getLogger(__name__)


def configure_tracing(
    service_name: str = "pingce-platform",
    *,
    exporter: SpanExporter | None = None,
    sampler_ratio: float | None = None,
) -> trace.Tracer:
    global _CONFIGURED, _PROVIDER
    if sampler_ratio is not None and not 0 <= sampler_ratio <= 1:
        raise ValueError("sampler_ratio must be between 0 and 1")
    if _CONFIGURED and exporter is None and sampler_ratio is None:
        return trace.get_tracer(service_name)

    if exporter is None:
        endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
        if endpoint:
            try:
                from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

                exporter = OTLPSpanExporter(endpoint=endpoint)
            except ImportError:
                _logger.warning("otlp_exporter_unavailable")

    sampler = ParentBased(TraceIdRatioBased(sampler_ratio)) if sampler_ratio is not None else None
    provider = TracerProvider(
        resource=Resource.create({"service.name": service_name}),
        sampler=sampler,
    )
    if exporter is not None:
        provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    _PROVIDER = provider
    _CONFIGURED = True
    return provider.get_tracer(service_name)


def flush_tracing() -> None:
    """Flush the last configured provider (used by tests and shutdown)."""
    if _PROVIDER is not None:
        _PROVIDER.force_flush()


def get_tracer(name: str = "pingce-platform") -> trace.Tracer:
    return trace.get_tracer(name)


def tracer(name: str = "pingce-platform") -> trace.Tracer:
    """Contract alias for ``get_tracer``."""
    return get_tracer(name)


def instrument_fastapi(app: object) -> None:
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    except ImportError:
        _logger.warning("fastapi_instrumentation_unavailable")
        return
    FastAPIInstrumentor.instrument_app(app)  # type: ignore[arg-type]


def instrument_celery(app: object) -> None:
    try:
        from opentelemetry.instrumentation.celery import CeleryInstrumentor
    except ImportError:
        _logger.warning("celery_instrumentation_unavailable")
        return
    CeleryInstrumentor().instrument(app=app)
