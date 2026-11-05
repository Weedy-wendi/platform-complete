"""Target configuration schema and template rendering.

Only whitelisted variables and whole-object placeholders are supported. There is
no expression evaluation, which prevents template injection from reaching an
adapter.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import jsonschema

from app.core.errors import InvalidArgumentError

TEMPLATE_VARIABLES = ("sample_key", "input", "expected", "trace_id")
_PLACEHOLDER = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")
_SENSITIVE_KEYS = {"password", "passwd", "secret", "token", "api_key", "api-key", "authorization", "x-api-key"}

TARGET_CONFIG_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["adapter", "config_version"],
    "additionalProperties": False,
    "properties": {
        "adapter": {"type": "string", "minLength": 1},
        "config_version": {"type": "string", "minLength": 1},
        "adapter_version": {"type": "string", "minLength": 1},
        "protocol": {"enum": ["http", "openai"]},
        "url": {"type": "string"},
        "method": {"enum": ["GET", "POST", "PUT", "PATCH"]},
        "headers": {"type": "object", "additionalProperties": {"type": "string"}},
        "body": {},
        "response": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "output": {"type": "string"},
                "trace_id": {"type": "string"},
                "usage": {"type": "string"},
                "finish_reason": {"type": "string"},
                "raw_ref": {"type": "string"},
            },
        },
        "auth_ref": {"type": "string", "pattern": "^secret://"},
        "timeout_seconds": {"type": "number", "exclusiveMinimum": 0, "maximum": 600},
        "max_retries": {"type": "integer", "minimum": 0, "maximum": 5},
        "retry_statuses": {"type": "array", "items": {"type": "integer"}},
        "model": {"type": "string"},
        "temperature": {"type": "number"},
        "seed": {"type": "integer"},
        "system_prompt": {"type": "string"},
    },
}


@dataclass(frozen=True)
class TargetConfig:
    adapter: str
    config_version: str
    adapter_version: str = "1"
    protocol: str = "http"
    url: str = ""
    method: str = "POST"
    headers: dict[str, str] = field(default_factory=dict)
    body: Any = None
    response: dict[str, str] = field(default_factory=dict)
    auth_ref: str | None = None
    timeout_seconds: float = 30.0
    max_retries: int = 2
    retry_statuses: tuple[int, ...] = (429, 500, 502, 503, 504)
    model: str | None = None
    temperature: float = 0.0
    seed: int | None = None
    system_prompt: str | None = None

    @property
    def version(self) -> str:
        return self.config_version


def _reject_plaintext_secrets(value: Any, path: str = "") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            lowered = str(key).lower()
            if lowered in _SENSITIVE_KEYS:
                if not (isinstance(item, str) and item.startswith("secret://")):
                    raise InvalidArgumentError("target config must use secret references", key=path or str(key))
            _reject_plaintext_secrets(item, f"{path}.{key}" if path else str(key))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _reject_plaintext_secrets(item, f"{path}[{index}]")


def validate_target_config(raw: dict[str, Any]) -> TargetConfig:
    if not isinstance(raw, dict):
        raise InvalidArgumentError("target config must be an object")
    _reject_plaintext_secrets(raw)
    errors = sorted(jsonschema.Draft202012Validator(TARGET_CONFIG_SCHEMA).iter_errors(raw), key=lambda e: list(e.path))
    if errors:
        first = errors[0]
        raise InvalidArgumentError(
            "target config is invalid",
            path=".".join(str(part) for part in first.path),
            reason=first.message,
        )
    return TargetConfig(
        adapter=raw["adapter"],
        config_version=raw["config_version"],
        adapter_version=str(raw.get("adapter_version") or "1"),
        protocol=raw.get("protocol") or ("openai" if raw["adapter"] == "openai_compat" else "http"),
        url=raw.get("url", ""),
        method=raw.get("method", "POST"),
        headers=dict(raw.get("headers") or {}),
        body=raw.get("body"),
        response=dict(raw.get("response") or {}),
        auth_ref=raw.get("auth_ref"),
        timeout_seconds=float(raw.get("timeout_seconds", 30.0)),
        max_retries=int(raw.get("max_retries", 2)),
        retry_statuses=tuple(int(item) for item in raw.get("retry_statuses", (429, 500, 502, 503, 504))),
        model=raw.get("model"),
        temperature=float(raw.get("temperature", 0.0)),
        seed=raw.get("seed"),
        system_prompt=raw.get("system_prompt"),
    )


def render_template(value: Any, variables: dict[str, Any]) -> Any:
    """Render ``{{ var }}`` placeholders using only whitelisted variables."""

    if isinstance(value, dict):
        return {key: render_template(item, variables) for key, item in value.items()}
    if isinstance(value, list):
        return [render_template(item, variables) for item in value]
    if not isinstance(value, str):
        return value
    matches = list(_PLACEHOLDER.finditer(value))
    if not matches:
        if "{{" in value or "}}" in value:
            raise InvalidArgumentError("template syntax is invalid")
        return value
    for match in matches:
        name = match.group(1)
        if name not in TEMPLATE_VARIABLES:
            raise InvalidArgumentError("template variable is not allowed", variable=name)
        if name not in variables:
            raise InvalidArgumentError("template variable has no value", variable=name)
    whole = _PLACEHOLDER.fullmatch(value)
    if whole is not None:
        return variables[whole.group(1)]
    return _PLACEHOLDER.sub(lambda match: str(variables[match.group(1)]), value)
