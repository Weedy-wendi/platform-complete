"""TraceSource protocol, OTLP/OpenInference normalization and deduplication."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from app.core.context import TenantContext
from app.core.errors import NotFoundError
from app.modules.evaluation.types import NormalizedTrace, TraceSource, TraceSpan


def _attributes(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return {str(key): value for key, value in raw.items()}
    if isinstance(raw, list):
        result: dict[str, Any] = {}
        for item in raw:
            if not isinstance(item, dict):
                continue
            key = item.get("key") or item.get("name")
            if not key:
                continue
            value = item.get("value")
            if isinstance(value, dict):
                if "stringValue" in value:
                    value = value["stringValue"]
                elif "intValue" in value:
                    value = int(value["intValue"])
                elif "doubleValue" in value:
                    value = float(value["doubleValue"])
                elif "boolValue" in value:
                    value = bool(value["boolValue"])
            result[str(key)] = value
        return result
    return {}


def _status(raw: Any) -> str:
    if isinstance(raw, dict):
        code = raw.get("code")
        if code in (0, "0", "UNSET", "STATUS_CODE_UNSET"):
            return "unset"
        if code in (1, "1", "OK", "STATUS_CODE_OK"):
            return "ok"
        if code in (2, "2", "ERROR", "STATUS_CODE_ERROR"):
            return "error"
        return str(code or "unset")
    return str(raw or "unset")


def _otlp_span(raw: dict[str, Any], tenant_id: str) -> TraceSpan | None:
    trace_id = raw.get("traceId") or raw.get("trace_id")
    span_id = raw.get("spanId") or raw.get("span_id")
    if not trace_id or not span_id:
        return None
    return TraceSpan(
        trace_id=str(trace_id),
        span_id=str(span_id),
        parent_span_id=raw.get("parentSpanId") or raw.get("parent_span_id"),
        name=str(raw.get("name") or ""),
        kind=str(raw.get("kind") or "internal"),
        start_time_ns=int(raw.get("startTimeUnixNano") or raw.get("start_time_unix_nano") or 0),
        end_time_ns=int(raw.get("endTimeUnixNano") or raw.get("end_time_unix_nano") or 0),
        attributes=_attributes(raw.get("attributes")),
        status=_status(raw.get("status")),
        tenant_id=tenant_id,
    )


def normalize_otlp_spans(payload: Any, tenant_id: str) -> NormalizedTrace:
    """Normalize an OTLP/JSON payload (or a bare span list)."""

    spans: list[TraceSpan] = []
    issues: list[str] = []
    raw_spans: list[dict[str, Any]] = []
    if isinstance(payload, dict):
        resource_spans = payload.get("resourceSpans") or payload.get("resource_spans")
        if isinstance(resource_spans, list):
            for resource in resource_spans:
                if not isinstance(resource, dict):
                    continue
                scopes = resource.get("scopeSpans") or resource.get("instrumentationLibrarySpans") or []
                for scope in scopes if isinstance(scopes, list) else []:
                    if not isinstance(scope, dict):
                        continue
                    for item in scope.get("spans", []) or []:
                        if isinstance(item, dict):
                            raw_spans.append(item)
        elif "spans" in payload and isinstance(payload["spans"], list):
            raw_spans = [item for item in payload["spans"] if isinstance(item, dict)]
        elif "traceId" in payload or "trace_id" in payload:
            raw_spans = [payload]
    elif isinstance(payload, list):
        raw_spans = [item for item in payload if isinstance(item, dict)]

    trace_id = ""
    for raw in raw_spans:
        span = _otlp_span(raw, tenant_id)
        if span is None:
            issues.append("span is missing trace_id or span_id")
            continue
        trace_id = trace_id or span.trace_id
        if span.tenant_id and tenant_id and span.tenant_id != tenant_id:
            issues.append("span belongs to another tenant")
            continue
        spans.append(span)
    deduped = dedupe_spans(spans)
    if len(deduped) != len(spans):
        issues.append("duplicate spans removed")
    return NormalizedTrace(
        trace_id=trace_id,
        spans=deduped,
        issues=issues,
        degraded=bool(issues) or not deduped,
    )


def normalize_openinference_spans(payload: Any, tenant_id: str) -> NormalizedTrace:
    """Accept the common OpenInference ``spans`` list with snake_case fields."""

    if isinstance(payload, dict) and isinstance(payload.get("spans"), list):
        raw_spans = payload["spans"]
    elif isinstance(payload, list):
        raw_spans = payload
    else:
        raw_spans = []
    spans: list[TraceSpan] = []
    issues: list[str] = []
    trace_id = ""
    for raw in raw_spans:
        if not isinstance(raw, dict):
            issues.append("span is not an object")
            continue
        span = _otlp_span(raw, tenant_id)
        if span is None:
            issues.append("span is missing trace_id or span_id")
            continue
        trace_id = trace_id or span.trace_id
        spans.append(span)
    deduped = dedupe_spans(spans)
    if len(deduped) != len(spans):
        issues.append("duplicate spans removed")
    return NormalizedTrace(
        trace_id=trace_id,
        spans=deduped,
        issues=issues,
        degraded=bool(issues) or not deduped,
    )


def dedupe_spans(spans: list[TraceSpan]) -> list[TraceSpan]:
    seen: set[tuple[str, str]] = set()
    result: list[TraceSpan] = []
    for span in spans:
        key = (span.trace_id, span.span_id)
        if key in seen:
            continue
        seen.add(key)
        result.append(span)
    return result


class StaticTraceSource:
    """TraceSource backed by an in-memory provider (tests, offline import)."""

    def __init__(self, traces: Mapping[str, Any]) -> None:
        self._traces = traces

    def fetch(self, ctx: TenantContext, trace_id: str) -> list[TraceSpan]:
        if trace_id not in self._traces:
            raise NotFoundError("Trace not found", trace_id=trace_id)
        normalized = normalize_otlp_spans(self._traces[trace_id], ctx.tenant_id)
        return [span for span in normalized.spans if not span.tenant_id or span.tenant_id == ctx.tenant_id]


def normalize_trace(source: TraceSource, ctx: TenantContext, trace_id: str) -> NormalizedTrace:
    """Fetch and normalize without leaking provider-specific shapes upward."""

    try:
        spans = source.fetch(ctx, trace_id)
    except NotFoundError:
        return NormalizedTrace(trace_id=trace_id, spans=[], issues=["trace not found"], degraded=True)
    deduped = dedupe_spans(spans)
    issues = [] if deduped else ["trace has no spans"]
    if len(deduped) != len(spans):
        issues.append("duplicate spans removed")
    return NormalizedTrace(trace_id=trace_id, spans=deduped, issues=issues, degraded=bool(issues))


def span_duration_ms(span: TraceSpan) -> float | None:
    if span.start_time_ns and span.end_time_ns and span.end_time_ns >= span.start_time_ns:
        return (span.end_time_ns - span.start_time_ns) / 1_000_000
    return None


def span_started_at(span: TraceSpan) -> datetime | None:
    if not span.start_time_ns:
        return None
    return datetime.fromtimestamp(span.start_time_ns / 1_000_000_000, tz=UTC)
