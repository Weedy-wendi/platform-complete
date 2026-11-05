"""Error registry and mapping tests (CORE-12)."""

from __future__ import annotations

import pytest

import app.modules.evaluation.types  # noqa: F401  (registers BudgetExceededError)
from app.core.errors import (
    ERROR_CODE_SPECS,
    AppError,
    ForbiddenError,
    InvalidArgumentError,
    RateLimitedError,
    get_error_spec,
    to_http_problem,
    to_jsonrpc_error,
)


def _all_subclasses(cls: type[AppError]) -> list[type[AppError]]:
    result: list[type[AppError]] = []
    for subclass in cls.__subclasses__():
        result.append(subclass)
        result.extend(_all_subclasses(subclass))
    return result


def _error_instances() -> dict[str, AppError]:
    instances: dict[str, AppError] = {}
    for cls in _all_subclasses(AppError):
        try:
            instance = cls()
        except TypeError:
            # RateLimitedError requires retry_after.
            instance = cls(1)
        instances[instance.code] = instance
    return instances


def test_registry_covers_every_error_class() -> None:
    assert set(_error_instances()) == set(ERROR_CODE_SPECS)


@pytest.mark.parametrize(
    ("spec", "error"),
    [pytest.param(spec, _error_instances()[code], id=code) for code, spec in ERROR_CODE_SPECS.items()],
)
def test_http_and_jsonrpc_mapping_matches_registry(spec, error: AppError) -> None:
    assert error.http_status == spec.http_status
    assert error.retryable == spec.retryable
    assert to_jsonrpc_error(error, trace_id="trace")["code"] == spec.jsonrpc_code

    problem = to_http_problem(error, trace_id="trace")["error"]
    assert problem["code"] == spec.code
    assert problem["trace_id"] == "trace"
    assert "traceback" not in str(problem).lower()


def test_registry_contains_all_contract_codes() -> None:
    assert {
        "UNAUTHORIZED",
        "FORBIDDEN",
        "NOT_FOUND",
        "INVALID_CURSOR",
        "INVALID_ARGUMENT",
        "RATE_LIMITED",
        "RESULT_TOO_LARGE",
        "UPSTREAM_UNAVAILABLE",
        "SERVICE_UNAVAILABLE",
        "INTERNAL",
    } <= set(ERROR_CODE_SPECS)


def test_unknown_code_falls_back_to_server_error() -> None:
    assert get_error_spec("MISSING") is None
    assert to_jsonrpc_error(ForbiddenError())["code"] == -32000
    assert to_jsonrpc_error(InvalidArgumentError())["code"] == -32602
    assert to_jsonrpc_error(RateLimitedError(7))["code"] == -32000


def test_error_does_not_leak_internal_details() -> None:
    payload = to_jsonrpc_error(ForbiddenError(required_scope="mcp:eval:read"), trace_id="abc")
    assert payload["data"]["code"] == "FORBIDDEN"
    assert payload["data"]["required_scope"] == "mcp:eval:read"
    assert "traceback" not in str(payload).lower()
