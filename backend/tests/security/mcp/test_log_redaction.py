"""Log and audit redaction tests (FR-028, T064)."""

from __future__ import annotations

import json
import logging
from dataclasses import fields

from app.core.logging import JsonFormatter
from app.core.logging import redact_text as log_redact
from app.mcp.limits import redact_mapping
from app.modules.audit.public import AuditEvent


def test_bearer_and_api_key_are_redacted() -> None:
    secret = "pk_live_0123456789abcdef01234567_secretvalue"
    text = f"Authorization: Bearer {secret}"
    redacted = log_redact(text)
    assert secret not in redacted
    assert "REDACTED" in redacted


def test_email_and_phone_are_redacted() -> None:
    redacted = log_redact("contact alice@example.com or 13800138000")
    assert "alice@example.com" not in redacted
    assert "13800138000" not in redacted
    assert "[EMAIL]" in redacted
    assert "[PHONE]" in redacted


def test_formatter_redacts_message() -> None:
    formatter = JsonFormatter()
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="token=sk_live_abcdefgh12345678 email=alice@example.com",
        args=(),
        exc_info=None,
    )
    payload = json.loads(formatter.format(record))
    assert "sk_live_abcdefgh12345678" not in payload["message"]
    assert "alice@example.com" not in payload["message"]


def test_audit_event_carries_no_content_fields() -> None:
    names = {item.name for item in fields(AuditEvent)}
    forbidden = {"arguments", "result", "prompt", "sample", "payload", "api_key", "content"}
    assert names.isdisjoint(forbidden)


def test_sample_redaction_handles_sensitive_keys() -> None:
    payload = {
        "password": "hunter2",
        "api_key": "sk_live_abcdefgh12345678",
        "note": "email alice@example.com",
    }
    redacted = redact_mapping(payload)
    assert redacted["password"] == "[REDACTED]"
    assert redacted["api_key"] == "[REDACTED]"
    assert "alice@example.com" not in redacted["note"]
