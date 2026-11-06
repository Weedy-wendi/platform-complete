"""LLM-as-judge evaluator with a ModelGateway-like Protocol.

The judge never writes database rows. It returns a structured outcome and the
run executor records ``judge_call`` evidence, which keeps this module testable
without a gateway or a database.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Protocol

import jsonschema

from app.core.context import TenantContext
from app.core.errors import InvalidArgumentError

JUDGE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["reasoning"],
    "anyOf": [{"required": ["score"]}, {"required": ["rating"]}],
    "properties": {
        "score": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "rating": {"type": "number", "minimum": 1.0, "maximum": 5.0},
        "reasoning": {"type": "string", "minLength": 1},
        "label": {"type": "string"},
        "criteria": {"type": "object"},
    },
    "additionalProperties": True,
}


@dataclass(frozen=True)
class JudgeModelRequest:
    model: str
    messages: list[dict[str, Any]]
    temperature: float = 0.0
    seed: int | None = None
    timeout_seconds: float = 30.0


@dataclass(frozen=True)
class JudgeModelResponse:
    text: str
    usage: dict[str, int] = field(default_factory=dict)
    cost_usd: float = 0.0
    raw_ref: str | None = None
    finish_reason: str | None = None


class JudgeModelGateway(Protocol):
    def complete(self, ctx: TenantContext, request: JudgeModelRequest) -> JudgeModelResponse: ...


@dataclass(frozen=True)
class JudgeOutcome:
    score: float
    passed: bool
    reasoning: str
    parsed: dict[str, Any]
    raw_text: str
    prompt_messages: list[dict[str, Any]]
    model: str
    usage: dict[str, int] = field(default_factory=dict)
    cost_usd: float = 0.0
    raw_ref: str | None = None


def _strip_fence(text: str) -> str:
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    lines = stripped.splitlines()
    if lines:
        lines = lines[1:]
    if lines and lines[-1].strip().startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines).strip()


def parse_judge_output(text: str) -> dict[str, Any]:
    """Parse and schema-validate a judge response.

    Judges sometimes wrap JSON in markdown fences or add prose; we accept the
    first JSON object but reject anything that does not satisfy the schema.
    """

    if not isinstance(text, str) or not text.strip():
        raise InvalidArgumentError("judge output is empty")
    candidate = _strip_fence(text)
    start = candidate.find("{")
    end = candidate.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise InvalidArgumentError("judge output is not a JSON object")
    try:
        parsed = json.loads(candidate[start : end + 1])
    except json.JSONDecodeError as exc:
        raise InvalidArgumentError("judge output is not valid JSON", reason=str(exc)) from exc
    if not isinstance(parsed, dict):
        raise InvalidArgumentError("judge output must be a JSON object")
    try:
        jsonschema.validate(instance=parsed, schema=JUDGE_SCHEMA)
    except jsonschema.ValidationError as exc:
        raise InvalidArgumentError("judge output failed schema validation", reason=exc.message) from exc
    if "score" in parsed:
        score = float(parsed["score"])
    else:
        score = float(parsed["rating"]) / 5.0
    normalized = dict(parsed)
    normalized["score"] = score
    normalized["reasoning"] = str(parsed["reasoning"])
    return normalized


def build_judge_messages(rubric: str, input_text: str, output_text: str) -> list[dict[str, Any]]:
    if not rubric.strip():
        raise InvalidArgumentError("judge rubric is required")
    return [
        {
            "role": "system",
            "content": (
                "You are an impartial evaluation judge. Return only a JSON object with "
                '{"score": <0..1>, "reasoning": <string>} and optional "label"/"criteria".'
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {"rubric": rubric, "input": input_text, "output": output_text},
                ensure_ascii=False,
                sort_keys=True,
            ),
        },
    ]


class JudgeEvaluator:
    def __init__(
        self,
        gateway: JudgeModelGateway,
        *,
        model: str = "judge",
        temperature: float = 0.0,
        timeout_seconds: float = 30.0,
    ) -> None:
        self._gateway = gateway
        self._model = model
        self._temperature = temperature
        self._timeout_seconds = timeout_seconds

    def evaluate(
        self,
        ctx: TenantContext,
        *,
        rubric: str,
        input_text: str,
        output_text: str,
        threshold: float = 0.7,
        model: str | None = None,
        seed: int | None = None,
    ) -> JudgeOutcome:
        if not 0.0 <= threshold <= 1.0:
            raise InvalidArgumentError("judge threshold must be between 0 and 1")
        messages = build_judge_messages(rubric, input_text, output_text)
        selected_model = model or self._model
        response = self._gateway.complete(
            ctx,
            JudgeModelRequest(
                model=selected_model,
                messages=messages,
                temperature=self._temperature,
                seed=seed,
                timeout_seconds=self._timeout_seconds,
            ),
        )
        parsed = parse_judge_output(response.text)
        score = float(parsed["score"])
        return JudgeOutcome(
            score=score,
            passed=score >= threshold,
            reasoning=str(parsed["reasoning"]),
            parsed=parsed,
            raw_text=response.text,
            prompt_messages=messages,
            model=selected_model,
            usage=dict(response.usage),
            cost_usd=float(response.cost_usd),
            raw_ref=response.raw_ref,
        )


class StaticJudgeGateway:
    """Deterministic gateway used by tests and local development."""

    def __init__(self, text: str) -> None:
        self._text = text

    def complete(self, ctx: TenantContext, request: JudgeModelRequest) -> JudgeModelResponse:
        return JudgeModelResponse(text=self._text)
