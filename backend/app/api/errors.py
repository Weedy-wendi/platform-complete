"""Map domain errors to the REST error envelope.

The public error contract is ``{code, message, trace_id, details}``. Business
modules only raise :class:`AppError` subclasses; this module owns HTTP status
selection and header handling. Stack traces, SQL and paths never leave the
process.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.requests import Request

from app.core.errors import AppError
from app.core.ids import new_trace_id
from app.core.logging import get_logger

logger = get_logger(__name__)

# Codes that have protocol-specific status semantics in core (MCP uses 200 for
# many of them) are normalised here for HTTP.
_STATUS_BY_CODE: dict[str, int] = {
    "TENANT_REQUIRED": 401,
    "UNAUTHORIZED": 401,
    "FORBIDDEN": 403,
    "NOT_FOUND": 404,
    "CONFLICT": 409,
    "INVALID_CURSOR": 409,
    "VALIDATION_ERROR": 400,
    "INVALID_ARGUMENT": 400,
    "UNPROCESSABLE": 422,
    "RATE_LIMITED": 429,
    "RESULT_TOO_LARGE": 413,
    "REQUEST_TOO_LARGE": 413,
    "UPSTREAM_UNAVAILABLE": 503,
    "SERVICE_UNAVAILABLE": 503,
    "INTERNAL": 500,
}


def validation_error(message: str = "Invalid request", **details: Any) -> AppError:
    return AppError("VALIDATION_ERROR", message, 400, False, details)


def conflict_error(message: str = "Conflict", **details: Any) -> AppError:
    return AppError("CONFLICT", message, 409, False, details)


def unprocessable_error(message: str = "Unprocessable request", **details: Any) -> AppError:
    return AppError("UNPROCESSABLE", message, 422, False, details)


def rest_status_for(error: AppError) -> int:
    mapped = _STATUS_BY_CODE.get(error.code)
    if mapped is not None:
        return mapped
    if 400 <= error.http_status <= 599:
        return error.http_status
    return 400


def trace_id_for(request: Request) -> str:
    trace_id = getattr(request.state, "trace_id", None)
    return str(trace_id) if trace_id else new_trace_id()


def error_body(error: AppError, trace_id: str) -> dict[str, Any]:
    details: dict[str, Any] = {"retryable": error.retryable, **error.details}
    return {
        "code": error.code,
        "message": error.message,
        "trace_id": trace_id,
        "details": details,
    }


def app_error_response(error: AppError, trace_id: str) -> JSONResponse:
    status = rest_status_for(error)
    headers: dict[str, str] = {"X-Trace-Id": trace_id}
    if status == 401:
        headers["WWW-Authenticate"] = 'Bearer realm="pingce"'
    if status == 429:
        retry_after = error.details.get("retry_after")
        if retry_after is not None:
            headers["Retry-After"] = str(retry_after)
    return JSONResponse(error_body(error, trace_id), status_code=status, headers=headers)


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(request: Request, exc: AppError) -> JSONResponse:
        return app_error_response(exc, trace_id_for(request))

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        errors = [
            {
                "loc": [str(part) for part in item.get("loc", ())],
                "msg": str(item.get("msg", "invalid value")),
                "type": str(item.get("type", "value_error")),
            }
            for item in exc.errors()
        ]
        error = validation_error("Request validation failed", errors=errors)
        return app_error_response(error, trace_id_for(request))

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        status = exc.status_code
        code = {
            400: "VALIDATION_ERROR",
            401: "UNAUTHORIZED",
            403: "FORBIDDEN",
            404: "NOT_FOUND",
            409: "CONFLICT",
            429: "RATE_LIMITED",
        }.get(status, "INTERNAL" if status >= 500 else "VALIDATION_ERROR")
        message = {
            404: "Not found",
            405: "Method not allowed",
            401: "Unauthorized",
            403: "Forbidden",
        }.get(status, str(exc.detail) if isinstance(exc.detail, str) else "Request failed")
        error = AppError(code, message, status, status >= 500)
        return app_error_response(error, trace_id_for(request))

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        trace_id = trace_id_for(request)
        logger.exception("api_unhandled_error", extra={"trace_id": trace_id})
        return app_error_response(AppError("INTERNAL", "Internal error", 500, True), trace_id)


__all__ = [
    "app_error_response",
    "conflict_error",
    "error_body",
    "install_error_handlers",
    "rest_status_for",
    "trace_id_for",
    "unprocessable_error",
    "validation_error",
]
