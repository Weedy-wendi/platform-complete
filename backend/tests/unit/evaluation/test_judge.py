"""Judge parsing and structured output validation (EVL-03)."""

from __future__ import annotations

import pytest

from app.core.context import TenantContext
from app.core.errors import InvalidArgumentError
from app.modules.evaluation.judge import (
    JudgeEvaluator,
    JudgeModelRequest,
    JudgeModelResponse,
    StaticJudgeGateway,
    build_judge_messages,
    parse_judge_output,
)

_CTX = TenantContext(tenant_id="tenant-a", subject_id="user:1")


def test_parse_plain_json() -> None:
    parsed = parse_judge_output('{"score": 0.75, "reasoning": "mostly right"}')
    assert parsed["score"] == 0.75
    assert parsed["reasoning"] == "mostly right"


def test_parse_fenced_json_with_prose() -> None:
    text = 'Here is my verdict:\n```json\n{"score": 0.9, "reasoning": "good", "label": "pass"}\n```\n'
    parsed = parse_judge_output(text)
    assert parsed["score"] == 0.9
    assert parsed["label"] == "pass"


def test_parse_rating_scale() -> None:
    parsed = parse_judge_output('{"rating": 4, "reasoning": "solid"}')
    assert parsed["score"] == pytest.approx(0.8)


@pytest.mark.parametrize(
    "text",
    [
        "",
        "not json",
        '{"reasoning": "missing score"}',
        '{"score": 1.5, "reasoning": "out of range"}',
        '{"score": 0.5, "reasoning": ""}',
    ],
)
def test_parse_rejects_invalid_output(text: str) -> None:
    with pytest.raises(InvalidArgumentError):
        parse_judge_output(text)


def test_judge_evaluator_calls_gateway_with_rubric() -> None:
    captured: list[JudgeModelRequest] = []

    class RecordingGateway:
        def complete(self, ctx: TenantContext, request: JudgeModelRequest) -> JudgeModelResponse:
            captured.append(request)
            return JudgeModelResponse(
                text='{"score": 0.85, "reasoning": "clear and correct"}',
                usage={"prompt_tokens": 10, "completion_tokens": 5},
                cost_usd=0.001,
                raw_ref="artifact://judge/1",
            )

    judge = JudgeEvaluator(RecordingGateway(), model="judge-x")
    outcome = judge.evaluate(
        _CTX,
        rubric="Be correct",
        input_text="2+2?",
        output_text="4",
        threshold=0.8,
    )
    assert outcome.score == pytest.approx(0.85)
    assert outcome.passed is True
    assert outcome.cost_usd == 0.001
    assert outcome.raw_ref == "artifact://judge/1"
    assert captured[0].model == "judge-x"
    assert captured[0].messages[1]["content"].find("Be correct") >= 0


def test_judge_threshold_and_rubric_validation() -> None:
    judge = JudgeEvaluator(StaticJudgeGateway('{"score": 0.4, "reasoning": "weak"}'))
    outcome = judge.evaluate(_CTX, rubric="r", input_text="i", output_text="o", threshold=0.5)
    assert outcome.passed is False
    with pytest.raises(InvalidArgumentError):
        judge.evaluate(_CTX, rubric="", input_text="i", output_text="o")
    with pytest.raises(InvalidArgumentError):
        build_judge_messages("", "i", "o")
