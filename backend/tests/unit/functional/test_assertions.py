"""Assertion DSL and visual diff unit tests (FUN-02/04)."""

from __future__ import annotations

import pytest

from app.core.errors import InvalidArgumentError
from app.modules.functional.assertions import evaluate_assertion, resolve_json_path
from app.modules.functional.public import AssertionSpec, BrowserResult, HttpResponse
from app.modules.functional.visual import ImageData, compare_images


def test_status_code_assertion() -> None:
    outcome = evaluate_assertion(AssertionSpec("status_code", {"equals": 201}), HttpResponse(status_code=201))
    assert outcome.passed is True
    assert outcome.actual == 201


def test_json_path_assertion() -> None:
    response = HttpResponse(status_code=200, body={"data": {"items": [{"id": 7}]}})
    assert resolve_json_path("$.data.items[0].id", response.body) == 7
    outcome = evaluate_assertion(AssertionSpec("json_path", {"path": "$.data.items[0].id", "equals": 7}), response)
    assert outcome.passed is True


def test_json_path_missing_and_exists_assertion() -> None:
    response = HttpResponse(status_code=200, body={"data": {}})
    missing = evaluate_assertion(AssertionSpec("json_path", {"path": "$.data.id", "equals": 1}), response)
    assert missing.passed is False
    exists = evaluate_assertion(AssertionSpec("json_path", {"path": "$.data.id", "exists": False}), response)
    assert exists.passed is True


def test_duration_assertion() -> None:
    response = BrowserResult(status_code=200, duration_ms=2500)
    assert evaluate_assertion(AssertionSpec("duration_ms", {"max": 3000}), response).passed is True
    assert evaluate_assertion(AssertionSpec("duration_ms", {"max": 1000}), response).passed is False


def test_text_and_header_assertions() -> None:
    response = HttpResponse(status_code=200, body={"message": "all good"}, headers={"X-Trace": "t1"})
    assert evaluate_assertion(AssertionSpec("text_contains", {"text": "all good"}), response).passed is True
    assert evaluate_assertion(AssertionSpec("header", {"name": "x-trace", "equals": "t1"}), response).passed is True
    assert evaluate_assertion(AssertionSpec("unknown"), response).passed is False


def test_visual_diff_threshold() -> None:
    expected = ImageData(2, 2, (0, 0, 0, 0))
    same = ImageData(2, 2, (0, 0, 0, 0))
    changed = ImageData(2, 2, (0, 255, 0, 0))
    assert compare_images(expected, same).passed is True
    result = compare_images(expected, changed, threshold=0.01)
    assert result.passed is False
    assert result.mismatch_ratio == pytest.approx(0.25)
    assert result.diff_image == (0, 255, 0, 0)


def test_visual_diff_requires_matching_dimensions() -> None:
    with pytest.raises(InvalidArgumentError):
        compare_images(ImageData(1, 1, (0,)), ImageData(2, 1, (0, 0)))
