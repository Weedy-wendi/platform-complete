import pytest

from app.core.errors import ResultTooLargeError
from app.mcp.limits import cap_result, redact_text, truncate_utf8


def test_truncate_utf8_respects_byte_budget() -> None:
    value = "你好" * 1000
    result = truncate_utf8(value, 32)
    assert len(result.encode("utf-8")) <= 32
    assert result.endswith("…")


def test_cap_result_truncates_items() -> None:
    payload = {"items": [{"id": i, "text": "x" * 50} for i in range(100)]}
    capped, truncated = cap_result(payload, max_bytes=800)
    assert truncated is True
    assert capped["truncated"] is True
    assert len(capped["items"]) < 100


def test_cap_result_rejects_unreducible_object() -> None:
    with pytest.raises(ResultTooLargeError):
        cap_result({"text": "x" * 5000}, max_bytes=100)


def test_redact_text() -> None:
    assert "a@example.com" not in redact_text("contact a@example.com")
    assert "13800138000" not in redact_text("phone 13800138000")
    assert "pk_live" not in redact_text("key pk_live_abcdefgh12345678")
