"""Configurable data-quality rule evaluation (ING-07)."""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any

from app.modules.ingestion.public import (
    QualityCheckResult,
    QualityReport,
    QualityRuleSpec,
)


def _value_at(row: dict[str, Any], field: str) -> Any:
    value: Any = row
    for part in field.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    return value


def _evaluate_rule(rows: Sequence[dict[str, Any]], rule: QualityRuleSpec) -> QualityCheckResult:
    config = rule.config
    failed = 0
    details: dict[str, Any] = {}

    if rule.rule_type == "not_null":
        fields = config.get("fields") or ([config["field"]] if config.get("field") else [])
        failures: list[dict[str, Any]] = []
        for index, row in enumerate(rows):
            missing = [field for field in fields if _value_at(row, field) in (None, "")]
            if missing:
                failed += 1
                if len(failures) < 10:
                    failures.append({"row": index, "fields": missing})
        details = {"fields": fields, "samples": failures}

    elif rule.rule_type == "unique":
        fields = config.get("fields") or ([config["field"]] if config.get("field") else [])
        seen: dict[tuple[Any, ...], int] = {}
        duplicates: list[dict[str, Any]] = []
        for index, row in enumerate(rows):
            key = tuple(_value_at(row, field) for field in fields)
            if key in seen:
                failed += 1
                if len(duplicates) < 10:
                    duplicates.append({"row": index, "duplicate_of": seen[key], "key": list(key)})
            else:
                seen[key] = index
        details = {"fields": fields, "samples": duplicates}

    elif rule.rule_type == "range":
        field = str(config.get("field", ""))
        minimum = config.get("min")
        maximum = config.get("max")
        samples: list[dict[str, Any]] = []
        for index, row in enumerate(rows):
            value = _value_at(row, field)
            if value is None:
                continue
            if (minimum is not None and value < minimum) or (maximum is not None and value > maximum):
                failed += 1
                if len(samples) < 10:
                    samples.append({"row": index, "value": value})
        details = {"field": field, "min": minimum, "max": maximum, "samples": samples}

    elif rule.rule_type == "regex":
        field = str(config.get("field", ""))
        pattern = re.compile(str(config.get("pattern", "")))
        samples = []
        for index, row in enumerate(rows):
            value = _value_at(row, field)
            if value is None:
                continue
            if not pattern.search(str(value)):
                failed += 1
                if len(samples) < 10:
                    samples.append({"row": index, "value": str(value)[:120]})
        details = {"field": field, "pattern": pattern.pattern, "samples": samples}

    elif rule.rule_type == "min_rows":
        minimum = int(config.get("min", 1))
        if len(rows) < minimum:
            failed = minimum - len(rows)
        details = {"min": minimum, "rows": len(rows)}

    elif rule.rule_type == "max_fail_ratio":
        max_ratio = float(config.get("max", 0.0))
        failing_field = str(config.get("field", ""))
        invalid = sum(1 for row in rows if _value_at(row, failing_field) in (None, ""))
        failed = invalid
        ratio = invalid / len(rows) if rows else 0.0
        details = {"field": failing_field, "ratio": ratio, "max": max_ratio}
        if rows and ratio > max_ratio:
            return QualityCheckResult(
                rule_id=rule.rule_id,
                rule_type=rule.rule_type,
                passed=False,
                checked_rows=len(rows),
                failed_rows=invalid,
                details=details,
                severity=rule.severity,
            )
        return QualityCheckResult(
            rule_id=rule.rule_id,
            rule_type=rule.rule_type,
            passed=True,
            checked_rows=len(rows),
            failed_rows=invalid,
            details=details,
            severity=rule.severity,
        )

    else:
        return QualityCheckResult(
            rule_id=rule.rule_id,
            rule_type=rule.rule_type,
            passed=False,
            checked_rows=len(rows),
            failed_rows=len(rows),
            details={"error": f"unsupported rule type: {rule.rule_type}"},
            severity=rule.severity,
        )

    allowed_failures = int(config.get("max_failures", 0))
    return QualityCheckResult(
        rule_id=rule.rule_id,
        rule_type=rule.rule_type,
        passed=failed <= allowed_failures,
        checked_rows=len(rows),
        failed_rows=failed,
        details=details,
        severity=rule.severity,
    )


def evaluate_rules(
    rows: Sequence[dict[str, Any]],
    rules: Sequence[QualityRuleSpec],
) -> QualityReport:
    return QualityReport(results=tuple(_evaluate_rule(rows, rule) for rule in rules if rule.severity != "info"))
