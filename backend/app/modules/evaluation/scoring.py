"""Deterministic rule scorers: exact match, contains, regex and token F1."""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from app.core.errors import InvalidArgumentError


@dataclass(frozen=True)
class RuleScore:
    value: float
    passed: bool
    details: dict[str, Any] = field(default_factory=dict)


def _text(value: Any) -> str:
    if value is None:
        return ""
    return value if isinstance(value, str) else str(value)


def exact_match(
    expected: Any,
    actual: Any,
    *,
    case_sensitive: bool = True,
    strip: bool = True,
) -> RuleScore:
    left = _text(expected)
    right = _text(actual)
    if strip:
        left = left.strip()
        right = right.strip()
    if not case_sensitive:
        left = left.casefold()
        right = right.casefold()
    matched = left == right
    return RuleScore(
        value=1.0 if matched else 0.0,
        passed=matched,
        details={"expected": left, "actual": right, "case_sensitive": case_sensitive},
    )


def contains(
    expected: Any,
    actual: Any,
    *,
    case_sensitive: bool = False,
    strip: bool = False,
) -> RuleScore:
    needle = _text(expected)
    haystack = _text(actual)
    if strip:
        needle = needle.strip()
        haystack = haystack.strip()
    if not case_sensitive:
        needle = needle.casefold()
        haystack = haystack.casefold()
    matched = bool(needle) and needle in haystack
    return RuleScore(
        value=1.0 if matched else 0.0,
        passed=matched,
        details={"needle": needle, "case_sensitive": case_sensitive},
    )


_REGEX_FLAGS = {"i": re.IGNORECASE, "m": re.MULTILINE, "s": re.DOTALL, "x": re.VERBOSE}


def regex_match(
    expected: Any,
    actual: Any,
    *,
    flags: str = "",
    full_match: bool = False,
) -> RuleScore:
    pattern = _text(expected)
    text = _text(actual)
    if not pattern:
        raise InvalidArgumentError("regex pattern is required")
    unknown = set(flags) - set(_REGEX_FLAGS)
    if unknown:
        raise InvalidArgumentError("unsupported regex flags", flags=sorted(unknown))
    combined = 0
    for flag in flags:
        combined |= _REGEX_FLAGS[flag]
    try:
        compiled = re.compile(pattern, combined)
    except re.error as exc:
        raise InvalidArgumentError("invalid regex pattern", pattern=pattern, reason=str(exc)) from exc
    matched = bool(compiled.fullmatch(text) if full_match else compiled.search(text))
    return RuleScore(
        value=1.0 if matched else 0.0,
        passed=matched,
        details={"pattern": pattern, "matched": matched, "full_match": full_match},
    )


def _tokenize(text: str, tokenizer: Callable[[str], Sequence[str]] | None = None) -> list[str]:
    if tokenizer is not None:
        return [str(token) for token in tokenizer(text)]
    return [token for token in re.split(r"\s+", text.strip()) if token]


def token_f1(
    expected: Any,
    actual: Any,
    *,
    tokenizer: Callable[[str], Sequence[str]] | None = None,
    case_sensitive: bool = False,
) -> RuleScore:
    left = _text(expected)
    right = _text(actual)
    if not case_sensitive:
        left = left.casefold()
        right = right.casefold()
    expected_tokens = _tokenize(left, tokenizer)
    actual_tokens = _tokenize(right, tokenizer)
    if not expected_tokens and not actual_tokens:
        return RuleScore(1.0, True, {"precision": 1.0, "recall": 1.0, "f1": 1.0})
    if not expected_tokens or not actual_tokens:
        return RuleScore(
            0.0,
            False,
            {
                "precision": 0.0,
                "recall": 0.0,
                "f1": 0.0,
                "expected_tokens": len(expected_tokens),
                "actual_tokens": len(actual_tokens),
            },
        )
    expected_counts = Counter(expected_tokens)
    actual_counts = Counter(actual_tokens)
    overlap = sum(min(count, actual_counts[token]) for token, count in expected_counts.items())
    precision = overlap / len(actual_tokens)
    recall = overlap / len(expected_tokens)
    f1 = 0.0 if precision + recall == 0 else 2 * precision * recall / (precision + recall)
    return RuleScore(
        value=f1,
        passed=f1 >= 0.5,
        details={"precision": precision, "recall": recall, "f1": f1, "overlap": overlap},
    )


RULE_SCORERS: dict[str, Callable[..., RuleScore]] = {
    "exact_match": exact_match,
    "exact": exact_match,
    "contains": contains,
    "regex": regex_match,
    "regex_match": regex_match,
    "f1": token_f1,
    "token_f1": token_f1,
}


def score_rule(kind: str, *, expected: Any, actual: Any, config: dict[str, Any] | None = None) -> RuleScore:
    scorer = RULE_SCORERS.get(kind)
    if scorer is None:
        raise InvalidArgumentError("unknown rule evaluator", kind=kind, supported=sorted(RULE_SCORERS))
    options = dict(config or {})
    try:
        return scorer(expected, actual, **options)
    except TypeError as exc:
        raise InvalidArgumentError("invalid rule evaluator configuration", kind=kind, reason=str(exc)) from exc
