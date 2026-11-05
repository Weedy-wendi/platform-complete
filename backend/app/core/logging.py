"""Structured JSON logging with light redaction."""

from __future__ import annotations

import json
import logging
import re
from datetime import UTC, datetime
from typing import Any

from app.core.context import try_get_principal, try_get_tenant_context

_REDACTIONS = [
    (re.compile(r"Bearer\s+[A-Za-z0-9._~+/=-]+", re.IGNORECASE), "Bearer [REDACTED]"),
    (re.compile(r"\b(?:sk|pk)_[A-Za-z0-9._~-]{8,}"), "[SECRET]"),
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"), "[EMAIL]"),
    (re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"), "[PHONE]"),
]

_SENSITIVE_LOG_FIELDS = frozenset(
    {
        "prompt",
        "prompts",
        "sample",
        "samples",
        "input",
        "inputs",
        "output",
        "outputs",
        "content",
        "body",
        "messages",
    }
)


def redact_payload(value: Any) -> Any:
    """Recursively redact structured log payload fields."""
    if isinstance(value, dict):
        return {
            key: "[REDACTED]" if str(key).lower() in _SENSITIVE_LOG_FIELDS else redact_payload(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [redact_payload(item) for item in value]
    if isinstance(value, str):
        return redact_text(value)
    return value


def redact_text(value: str) -> str:
    result = value
    for pattern, replacement in _REDACTIONS:
        result = pattern.sub(replacement, result)
    return result


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        principal = try_get_principal()
        tenant = try_get_tenant_context()
        payload: dict[str, Any] = {
            "ts": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": redact_text(record.getMessage()),
            "trace_id": getattr(record, "trace_id", None) or (tenant.trace_id if tenant else None),
            "tenant_id": getattr(record, "tenant_id", None)
            or (tenant.tenant_id if tenant else None)
            or (principal.tenant_id if principal else None),
        }
        for key in ("tool", "status", "latency_ms", "result_bytes", "error_code", "sql"):
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = redact_text(value) if key == "sql" and isinstance(value, str) else value
        for key in _SENSITIVE_LOG_FIELDS:
            if getattr(record, key, None) is not None:
                payload[key] = "[REDACTED]"
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level.upper())


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
