"""Rule scorer boundaries (EVL-02)."""

from __future__ import annotations

import pytest

from app.core.errors import InvalidArgumentError
from app.modules.evaluation.scoring import (
    contains,
    exact_match,
    regex_match,
    score_rule,
    token_f1,
)


def test_exact_match_boundaries() -> None:
    assert exact_match("hello", "hello").value == 1.0
    assert exact_match("Hello", "hello").value == 0.0
    assert exact_match("Hello", "hello", case_sensitive=False).value == 1.0
    assert exact_match("  hello ", "hello").value == 1.0
    assert exact_match("  hello ", "hello", strip=False).value == 0.0
    assert exact_match(None, "").value == 1.0
    assert exact_match("a", "b").passed is False


def test_contains_is_case_insensitive_by_default() -> None:
    assert contains("world", "hello WORLD").value == 1.0
    assert contains("WORLD", "hello world", case_sensitive=True).value == 0.0
    assert contains("", "anything").value == 0.0
    assert contains("x", "x").details["needle"] == "x"


def test_regex_match_and_invalid_pattern() -> None:
    assert regex_match(r"ab\d+", "xx ab123").value == 1.0
    assert regex_match(r"^ab\d+$", "xx ab123").value == 0.0
    assert regex_match(r"ab\d+", "xx ab123", full_match=False).value == 1.0
    assert regex_match("HELLO", "hello", flags="i").value == 1.0
    with pytest.raises(InvalidArgumentError):
        regex_match("[", "value")
    with pytest.raises(InvalidArgumentError):
        regex_match("x", "value", flags="z")
    with pytest.raises(InvalidArgumentError):
        regex_match("", "value")


def test_token_f1_boundaries() -> None:
    assert token_f1("a b", "a b").value == 1.0
    assert token_f1("", "").value == 1.0
    assert token_f1("a", "b").value == 0.0
    assert token_f1("a", "").value == 0.0
    score = token_f1("a b", "a b c")
    assert score.value == pytest.approx(0.8)
    score = token_f1("a a b", "a b b")
    assert score.value == pytest.approx(2 / 3)
    assert token_f1("A", "a").value == 1.0
    assert token_f1("A", "a", case_sensitive=True).value == 0.0


def test_score_rule_dispatch_and_config_errors() -> None:
    assert score_rule("exact_match", expected="x", actual="x").value == 1.0
    assert score_rule("f1", expected="a b", actual="a b", config={}).value == 1.0
    with pytest.raises(InvalidArgumentError):
        score_rule("missing", expected="x", actual="x")
    with pytest.raises(InvalidArgumentError):
        score_rule("exact_match", expected="x", actual="x", config={"unknown": True})
