"""Replay adapter: reconstructs responses from recorded raw artifacts.

It never performs network calls. Missing artifacts fail the individual item so
the rest of the run can continue.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from typing import Any

from app.core.context import TenantContext
from app.core.errors import UpstreamUnavailableError
from app.modules.evaluation.types import AgentRequest, AgentResponse

ArtifactStore = Mapping[str, Any] | Callable[[str], Any]


def _parse_raw(raw: Any) -> Any:
    if isinstance(raw, bytes):
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return raw.decode("utf-8", errors="replace")
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return raw
    return raw


def _extract_output(raw: Any) -> str:
    value = _parse_raw(raw)
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        for key in ("output", "text", "content"):
            candidate = value.get(key)
            if isinstance(candidate, str):
                return candidate
        choices = value.get("choices")
        if isinstance(choices, list) and choices:
            message = choices[0].get("message") if isinstance(choices[0], dict) else None
            if isinstance(message, dict) and isinstance(message.get("content"), str):
                return message["content"]
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


class ReplayAdapter:
    def __init__(self, store: ArtifactStore | None = None) -> None:
        self._store = store if store is not None else {}

    def _lookup(self, key: str) -> Any:
        if callable(self._store):
            try:
                return self._store(key)
            except KeyError as exc:
                raise UpstreamUnavailableError(f"replay artifact is missing: {key}") from exc
        if key not in self._store:
            raise UpstreamUnavailableError(f"replay artifact is missing: {key}")
        return self._store[key]

    def invoke(self, ctx: TenantContext, request: AgentRequest) -> AgentResponse:
        key = request.raw_ref or request.payload.get("raw_ref") or request.sample_key
        raw = self._lookup(str(key))
        parsed = _parse_raw(raw)
        trace_id = None
        usage: dict[str, int] = {}
        if isinstance(parsed, dict):
            trace_id = parsed.get("trace_id") or parsed.get("id")
            usage_raw = parsed.get("usage")
            if isinstance(usage_raw, dict):
                usage = {str(name): int(value) for name, value in usage_raw.items() if isinstance(value, (int, float))}
        return AgentResponse(
            output=_extract_output(parsed),
            trace_id=str(trace_id) if trace_id is not None else request.trace_id,
            usage=usage,
            cost_usd=0.0,
            raw_ref=str(key),
            raw=parsed,
        )
