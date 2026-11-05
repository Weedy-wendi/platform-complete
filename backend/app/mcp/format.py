"""Formatting helpers shared by MCP tool and resource handlers."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from mcp import types

from app.core.clock import utcnow_naive
from app.core.errors import InvalidArgumentError


def isoformat_z(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.isoformat() + "Z"
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def as_of() -> str:
    return isoformat_z(utcnow_naive()) or ""


def parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise InvalidArgumentError("value must be an ISO 8601 datetime") from exc
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(UTC).replace(tzinfo=None)
    return parsed


def success(payload: dict[str, Any]) -> types.CallToolResult:
    return types.CallToolResult(
        content=[types.TextContent(text=json.dumps(payload, ensure_ascii=False, default=str))],
        structured_content=payload,
    )


def error(code: str, message: str, *, retryable: bool = False, **details: Any) -> types.CallToolResult:
    return types.CallToolResult(
        is_error=True,
        content=[types.TextContent(text=message)],
        structured_content={"code": code, "message": message, "retryable": retryable, **details},
    )


def drop_none(value: dict[str, Any]) -> dict[str, Any]:
    return {key: item for key, item in value.items() if item is not None}
