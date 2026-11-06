"""Domain errors and protocol mappings.

Business code raises domain errors. HTTP and MCP adapters translate them; no
business module should import FastAPI or construct JSON-RPC envelopes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class AppError(Exception):
    code: str
    message: str
    http_status: int = 400
    retryable: bool = False
    details: dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"


class TenantRequiredError(AppError):
    def __init__(self, message: str = "Tenant context is required") -> None:
        super().__init__("TENANT_REQUIRED", message, 401)


class UnauthorizedError(AppError):
    def __init__(self, message: str = "Unauthorized", **details: Any) -> None:
        super().__init__("UNAUTHORIZED", message, 401, False, details)


class ForbiddenError(AppError):
    def __init__(self, message: str = "Insufficient scope", **details: Any) -> None:
        super().__init__("FORBIDDEN", message, 403, False, details)


class NotFoundError(AppError):
    def __init__(self, message: str = "Not found", **details: Any) -> None:
        super().__init__("NOT_FOUND", message, 200, False, details)


class InvalidArgumentError(AppError):
    def __init__(self, message: str = "Invalid argument", **details: Any) -> None:
        super().__init__("INVALID_ARGUMENT", message, 200, False, details)


class InvalidCursorError(AppError):
    def __init__(self, message: str = "Invalid cursor") -> None:
        super().__init__("INVALID_CURSOR", message, 200, False)


class RateLimitedError(AppError):
    def __init__(self, retry_after: int, **details: Any) -> None:
        super().__init__(
            "RATE_LIMITED",
            "Rate limited",
            429,
            True,
            {"retry_after": retry_after, **details},
        )


class ResultTooLargeError(AppError):
    def __init__(self, message: str = "Result exceeds the size limit") -> None:
        super().__init__("RESULT_TOO_LARGE", message, 200, False)


class UpstreamUnavailableError(AppError):
    def __init__(self, message: str = "Upstream dependency is unavailable") -> None:
        super().__init__("UPSTREAM_UNAVAILABLE", message, 200, True)


class ServiceUnavailableError(AppError):
    def __init__(self, message: str = "Service dependency is unavailable") -> None:
        super().__init__("SERVICE_UNAVAILABLE", message, 503, True)


class InternalError(AppError):
    def __init__(self, message: str = "Internal error") -> None:
        super().__init__("INTERNAL", message, 500, True)


@dataclass(frozen=True)
class ErrorSpec:
    """Canonical HTTP/MCP mapping for one error code."""

    code: str
    http_status: int
    retryable: bool
    jsonrpc_code: int


ERROR_CODE_SPECS: dict[str, ErrorSpec] = {
    "TENANT_REQUIRED": ErrorSpec("TENANT_REQUIRED", 401, False, -32000),
    "UNAUTHORIZED": ErrorSpec("UNAUTHORIZED", 401, False, -32000),
    "FORBIDDEN": ErrorSpec("FORBIDDEN", 403, False, -32000),
    "NOT_FOUND": ErrorSpec("NOT_FOUND", 200, False, -32000),
    "INVALID_ARGUMENT": ErrorSpec("INVALID_ARGUMENT", 200, False, -32602),
    "INVALID_CURSOR": ErrorSpec("INVALID_CURSOR", 200, False, -32000),
    "RATE_LIMITED": ErrorSpec("RATE_LIMITED", 429, True, -32000),
    "RESULT_TOO_LARGE": ErrorSpec("RESULT_TOO_LARGE", 200, False, -32000),
    "UPSTREAM_UNAVAILABLE": ErrorSpec("UPSTREAM_UNAVAILABLE", 200, True, -32000),
    "SERVICE_UNAVAILABLE": ErrorSpec("SERVICE_UNAVAILABLE", 503, True, -32000),
    "INTERNAL": ErrorSpec("INTERNAL", 500, True, -32603),
    "BUDGET_EXCEEDED": ErrorSpec("BUDGET_EXCEEDED", 409, False, -32000),
}


def get_error_spec(code: str) -> ErrorSpec | None:
    return ERROR_CODE_SPECS.get(code)


def _jsonrpc_code(error: AppError) -> int:
    spec = ERROR_CODE_SPECS.get(error.code)
    return spec.jsonrpc_code if spec else -32000


def to_jsonrpc_error(error: AppError, *, trace_id: str | None = None) -> dict[str, Any]:
    data: dict[str, Any] = {
        "code": error.code,
        "retryable": error.retryable,
        "trace_id": trace_id,
    }
    data.update(error.details)
    return {
        "code": _jsonrpc_code(error),
        "message": error.message,
        "data": data,
    }


def to_http_problem(error: AppError, *, trace_id: str | None = None) -> dict[str, Any]:
    return {
        "error": {
            "code": error.code,
            "message": error.message,
            "retryable": error.retryable,
            "trace_id": trace_id,
            **error.details,
        }
    }
