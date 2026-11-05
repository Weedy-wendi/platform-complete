"""Health/readiness and observability primitives (OBS-01..05)."""

from __future__ import annotations

import json
import logging

import pytest
import yaml
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from sqlalchemy import create_engine

from app.core.health import check_database, check_redis, check_storage, liveness, readiness
from app.core.logging import JsonFormatter, redact_payload
from app.core.metrics import (
    AUDIT_WRITE_FAILED,
    HTTP_REQUESTS,
    JOB_QUEUE_DEPTH,
    MODEL_COST_USD,
    PLATFORM_READINESS_FAILURES,
)
from app.core.tracing import configure_tracing, flush_tracing, tracer
from tests.support.storage import FakeStorage


def test_structured_log_redacts_prompt_and_pii() -> None:
    record = logging.LogRecord("unit", logging.INFO, __file__, 1, "hello alice@example.com", None, None)
    record.prompt = "write a secret prompt"
    record.sample = {"text": "raw sample"}
    payload = json.loads(JsonFormatter().format(record))
    assert payload["prompt"] == "[REDACTED]"
    assert payload["sample"] == "[REDACTED]"
    assert "alice@example.com" not in payload["message"]


def test_redact_payload_recurses() -> None:
    payload = redact_payload({"messages": [{"content": "secret"}], "note": "a@example.com"})
    assert payload["messages"] == "[REDACTED]"
    assert payload["note"] == "[EMAIL]"


def test_health_checks_and_readiness() -> None:
    engine = create_engine("sqlite://")
    storage = FakeStorage()
    assert check_database(engine) is True
    assert check_storage(storage) is True

    class Redis:
        def ping(self) -> bool:
            return True

    assert check_redis(Redis()) is True
    assert liveness()[0] == 200

    status, body = readiness({"db": lambda: True, "redis": lambda: True})
    assert status == 200
    assert body["status"] == "ready"

    status, body = readiness({"db": lambda: False})
    assert status == 503
    assert body["checks"]["db"]["ok"] is False


def test_tracing_sampling_and_alias() -> None:
    full = InMemorySpanExporter()
    tracer_full = configure_tracing("pingce-full", exporter=full, sampler_ratio=1.0)
    with tracer_full.start_as_current_span("kept"):
        pass
    flush_tracing()
    assert [span.name for span in full.get_finished_spans()] == ["kept"]
    assert tracer("pingce-full") is not None


def test_metrics_are_registered() -> None:
    assert HTTP_REQUESTS._name == "http_requests"  # type: ignore[attr-defined]
    assert JOB_QUEUE_DEPTH._name == "job_queue_depth"  # type: ignore[attr-defined]
    assert MODEL_COST_USD._name == "model_cost_usd"  # type: ignore[attr-defined]
    assert AUDIT_WRITE_FAILED._name == "audit_write_failed"  # type: ignore[attr-defined]
    assert PLATFORM_READINESS_FAILURES._name == "platform_readiness_failures"  # type: ignore[attr-defined]


def test_alert_rules_parse_and_cover_platform_signals() -> None:
    from pathlib import Path

    path = Path(__file__).resolve().parents[4] / "deploy" / "prometheus" / "alerts.yaml"
    rules = yaml.safe_load(path.read_text(encoding="utf-8"))
    groups = {group["name"]: group for group in rules["groups"]}
    assert "pingce-platform" in groups
    alerts = {rule["alert"] for rule in groups["pingce-platform"]["rules"]}
    assert {
        "PlatformHighErrorRate",
        "PlatformP95LatencyHigh",
        "JobQueueBacklog",
        "ModelCostSpike",
        "AuditWriteFailures",
    } <= alerts


def test_bad_sampler_ratio_is_rejected() -> None:
    with pytest.raises(ValueError):
        configure_tracing("bad", sampler_ratio=1.5)
