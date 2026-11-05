from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from app.core.tracing import configure_tracing


def test_tracing_exports_spans() -> None:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = provider.get_tracer("unit")
    with tracer.start_as_current_span("unit.test"):
        pass
    spans = exporter.get_finished_spans()
    assert spans
    assert spans[-1].name == "unit.test"


def test_configure_tracing_returns_tracer() -> None:
    tracer = configure_tracing("pingce-unit")
    assert tracer is not None
