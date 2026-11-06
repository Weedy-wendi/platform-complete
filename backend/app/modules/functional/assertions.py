"""Assertion DSL evaluation (FUN-02)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from app.modules.functional.public import AssertionSpec, BrowserResult, HttpResponse

_MISSING = object()


@dataclass(frozen=True)
class AssertionOutcome:
    kind: str
    passed: bool
    expected: Any
    actual: Any
    message: str = ""
    config: dict[str, Any] = field(default_factory=dict)


def _body_of(response: HttpResponse | BrowserResult) -> Any:
    return response.body


def resolve_json_path(path: str, payload: Any) -> Any:
    """Resolve the JSONPath subset used by test cases: ``$.a[0].b``."""

    if path in {"", "$"}:
        return payload
    cursor = path[1:] if path.startswith("$") else path
    if cursor.startswith("."):
        cursor = cursor[1:]
    value = payload
    for raw_part in cursor.split("."):
        if not raw_part:
            continue
        part = raw_part
        while "[" in part:
            name, _, rest = part.partition("[")
            if name:
                if not isinstance(value, dict) or name not in value:
                    return _MISSING
                value = value[name]
            index_text, _, remainder = rest.partition("]")
            if not index_text.isdigit() or not isinstance(value, list):
                return _MISSING
            index = int(index_text)
            if index >= len(value):
                return _MISSING
            value = value[index]
            part = remainder
        if part:
            if not isinstance(value, dict) or part not in value:
                return _MISSING
            value = value[part]
    return value


def _as_text(body: Any) -> str:
    if isinstance(body, str):
        return body
    try:
        return json.dumps(body, ensure_ascii=False)
    except TypeError:
        return str(body)


def _outcome(
    spec: AssertionSpec,
    passed: bool,
    expected: Any,
    actual: Any,
    message: str,
) -> AssertionOutcome:
    return AssertionOutcome(spec.kind, passed, expected, actual, message, dict(spec.config))


def evaluate_assertion(
    spec: AssertionSpec,
    response: HttpResponse | BrowserResult,
) -> AssertionOutcome:
    config = spec.config
    body = _body_of(response)
    actual: Any = None

    if spec.kind == "status_code":
        expected = config.get("equals", config.get("status_code", 200))
        actual = response.status_code
        return _outcome(spec, actual == expected, expected, actual, f"status {actual} != {expected}")

    if spec.kind == "duration_ms":
        actual = response.duration_ms
        if "max" in config:
            expected = config["max"]
            passed = actual <= expected
            message = f"duration {actual}ms > {expected}ms"
        else:
            expected = config.get("equals", config.get("lte"))
            passed = actual == expected
            message = f"duration {actual}ms != {expected}ms"
        return _outcome(spec, passed, expected, actual, message)

    if spec.kind in {"json_path", "exists"}:
        path = str(config.get("path", "$"))
        resolved = resolve_json_path(path, body)
        exists_expected = bool(config.get("exists", "equals" not in config))
        exists = resolved is not _MISSING
        if "equals" in config:
            passed = exists and resolved == config["equals"]
            message = f"{path} value {resolved!r} != {config['equals']!r}"
        else:
            passed = exists == exists_expected
            message = f"{path} exists={exists}, expected={exists_expected}"
        actual = None if resolved is _MISSING else resolved
        return _outcome(spec, passed, config.get("equals", exists_expected), actual, message)

    if spec.kind in {"text_contains", "body_contains"}:
        needle = str(config.get("text", ""))
        actual = _as_text(body)
        passed = needle in actual
        return _outcome(spec, passed, needle, actual[:500], f"body does not contain {needle!r}")

    if spec.kind == "header":
        name = str(config.get("name", "")).lower()
        expected = config.get("equals")
        actual = {key.lower(): value for key, value in getattr(response, "headers", {}).items()}.get(name)
        return _outcome(spec, actual == expected, expected, actual, f"header {name}={actual!r}")

    return _outcome(spec, False, None, None, f"unsupported assertion kind: {spec.kind}")


def evaluate_assertions(
    specs: tuple[AssertionSpec, ...],
    response: HttpResponse | BrowserResult,
) -> list[AssertionOutcome]:
    return [evaluate_assertion(spec, response) for spec in specs]


def summarize(outcomes: list[AssertionOutcome]) -> str | None:
    if not outcomes:
        return None
    failed = [outcome for outcome in outcomes if not outcome.passed]
    if failed:
        return failed[0].message or f"{failed[0].kind} failed"
    return ", ".join(f"{outcome.kind}=passed" for outcome in outcomes)


__all__ = [
    "AssertionOutcome",
    "evaluate_assertion",
    "evaluate_assertions",
    "resolve_json_path",
    "summarize",
]
