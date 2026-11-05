"""OTLP/OpenInference span normalization, dedupe and degradation (EVL-15)."""

from __future__ import annotations

from app.core.context import TenantContext
from app.modules.evaluation.targets.trace import (
    StaticTraceSource,
    normalize_openinference_spans,
    normalize_otlp_spans,
    normalize_trace,
    span_duration_ms,
)

_CTX = TenantContext(tenant_id="tenant-a", subject_id="user:1")


def test_normalize_otlp_resource_spans_and_attributes() -> None:
    payload = {
        "resourceSpans": [
            {
                "scopeSpans": [
                    {
                        "spans": [
                            {
                                "traceId": "trace-1",
                                "spanId": "span-1",
                                "name": "llm.call",
                                "startTimeUnixNano": "1000000000",
                                "endTimeUnixNano": "1500000000",
                                "attributes": [
                                    {"key": "model", "value": {"stringValue": "demo"}},
                                    {"key": "tokens", "value": {"intValue": "12"}},
                                ],
                                "status": {"code": 1},
                            }
                        ]
                    }
                ]
            }
        ]
    }
    trace = normalize_otlp_spans(payload, "tenant-a")
    assert trace.trace_id == "trace-1"
    assert len(trace.spans) == 1
    assert trace.spans[0].attributes == {"model": "demo", "tokens": 12}
    assert trace.spans[0].status == "ok"
    assert span_duration_ms(trace.spans[0]) == 500.0
    assert trace.degraded is False


def test_normalize_dedupes_and_marks_duplicates() -> None:
    payload = {
        "spans": [
            {"trace_id": "trace-1", "span_id": "s1", "name": "first"},
            {"trace_id": "trace-1", "span_id": "s1", "name": "duplicate"},
        ]
    }
    trace = normalize_otlp_spans(payload, "tenant-a")
    assert len(trace.spans) == 1
    assert "duplicate spans removed" in trace.issues
    assert trace.degraded is True


def test_missing_spans_degrade_instead_of_raising() -> None:
    trace = normalize_otlp_spans({"spans": [{"name": "no ids"}]}, "tenant-a")
    assert trace.spans == []
    assert trace.degraded is True
    assert trace.issues


def test_openinference_and_missing_trace_source() -> None:
    trace = normalize_openinference_spans(
        [{"trace_id": "trace-2", "span_id": "s2", "name": "retrieve", "attributes": {"k": "v"}}],
        "tenant-a",
    )
    assert trace.trace_id == "trace-2"
    assert trace.spans[0].attributes == {"k": "v"}

    source = StaticTraceSource({})
    missing = normalize_trace(source, _CTX, "trace-missing")
    assert missing.degraded is True
    assert missing.spans == []
