"""Prometheus metrics for the MCP adapter."""

from __future__ import annotations

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest

MCP_TOOL_CALLS = Counter(
    "mcp_tool_calls_total",
    "MCP tool calls",
    ["tool", "status"],
)
MCP_TOOL_DURATION = Histogram(
    "mcp_tool_duration_seconds",
    "MCP tool call latency",
    ["tool"],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)
MCP_TOOL_RESULT_BYTES = Histogram(
    "mcp_tool_result_bytes",
    "MCP tool result size",
    ["tool"],
    buckets=(128, 512, 2048, 8192, 32768, 65536),
)
MCP_AUTH_FAILURES = Counter(
    "mcp_auth_failures_total",
    "MCP authentication failures",
    ["reason"],
)
MCP_RATE_LIMITED = Counter(
    "mcp_rate_limited_total",
    "MCP rate limited requests",
    ["scope"],
)
MCP_CURSOR_INVALID = Counter(
    "mcp_cursor_invalid_total",
    "MCP invalid cursors",
)
MCP_AUDIT_WRITE_FAILED = Counter(
    "mcp_audit_write_failed_total",
    "MCP audit write failures",
)
AUDIT_WRITE_FAILED = Counter(
    "audit_write_failed_total",
    "Platform audit log write failures",
)

HTTP_REQUESTS = Counter(
    "http_requests_total",
    "Platform HTTP requests",
    ["route", "method", "status"],
)
HTTP_REQUEST_DURATION = Histogram(
    "http_request_duration_seconds",
    "Platform HTTP request latency",
    ["route", "method"],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)
JOB_QUEUE_DEPTH = Gauge(
    "job_queue_depth",
    "Pending jobs by queue",
    ["queue"],
)
JOB_FAILURES = Counter(
    "job_failures_total",
    "Job failures by queue and reason",
    ["queue", "reason"],
)
MODEL_CALLS = Counter(
    "model_calls_total",
    "Model gateway calls",
    ["provider", "model", "status"],
)
MODEL_COST_USD = Counter(
    "model_cost_usd_total",
    "Model gateway cost in USD",
    ["provider", "model"],
)
PLATFORM_READINESS_FAILURES = Counter(
    "platform_readiness_failures_total",
    "Platform readiness check failures",
    ["dependency"],
)


def metrics_payload() -> tuple[bytes, str]:
    return generate_latest(), CONTENT_TYPE_LATEST
