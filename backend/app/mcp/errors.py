"""MCP error re-exports and helpers."""

from __future__ import annotations

from typing import Any

from app.core.errors import AppError, to_http_problem, to_jsonrpc_error

__all__ = ["AppError", "to_http_problem", "to_jsonrpc_error", "jsonrpc_error_body"]


def jsonrpc_error_body(error: AppError, *, request_id: Any = None, trace_id: str | None = None) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": to_jsonrpc_error(error, trace_id=trace_id),
    }
