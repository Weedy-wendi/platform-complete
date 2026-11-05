"""Configurable cleaning: field transforms, masking and stable dedupe (ING-09).

A transform mapping is ``{target_field: source}`` where ``source`` is either a
dot-path string or an object with ``from``, ``type``, ``default`` and ``mask``
attributes. Masking supports ``email``, ``phone`` and ``full``.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from typing import Any

from app.core.errors import InvalidArgumentError

_MASK_KINDS = {"email", "phone", "full"}
_COERCE_TYPES = {"string", "integer", "int", "number", "float", "boolean", "bool"}


def value_at(row: dict[str, Any], path: str) -> Any:
    value: Any = row
    for part in path.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    return value


def validate_transform(transform: dict[str, Any] | None) -> None:
    if transform is None:
        return
    if not isinstance(transform, dict):
        raise InvalidArgumentError("transform must be a mapping")
    for target, spec in transform.items():
        if not isinstance(target, str) or not target.strip():
            raise InvalidArgumentError("transform target must be a non-empty field name")
        if isinstance(spec, str):
            continue
        if not isinstance(spec, dict):
            raise InvalidArgumentError("transform spec must be a source path or object", field=target)
        mask = spec.get("mask")
        if mask is not None and str(mask).lower() not in _MASK_KINDS:
            raise InvalidArgumentError("unsupported mask kind", field=target, mask=mask)
        kind = spec.get("type")
        if kind is not None and str(kind).lower() not in _COERCE_TYPES:
            raise InvalidArgumentError("unsupported transform type", field=target, type=kind)


def _coerce(value: Any, kind: str) -> Any:
    lowered = kind.lower()
    try:
        if lowered == "string":
            return str(value)
        if lowered in {"integer", "int"}:
            return int(value)
        if lowered in {"number", "float"}:
            return float(value)
        if lowered in {"boolean", "bool"}:
            if isinstance(value, str):
                return value.strip().lower() in {"1", "true", "yes", "y"}
            return bool(value)
    except (TypeError, ValueError) as exc:
        raise InvalidArgumentError("transform value cannot be converted", value=str(value), type=kind) from exc
    return value


def _mask(value: Any, kind: str) -> str:
    text = str(value)
    lowered = kind.lower()
    if lowered == "full":
        return "***"
    if lowered == "email":
        name, _, domain = text.partition("@")
        if not domain:
            return "***"
        return f"{name[:1]}***@{domain}"
    digits = "".join(char for char in text if char.isdigit())
    if len(digits) < 7:
        return "***"
    return f"{digits[:3]}****{digits[-4:]}"


def apply_transform(
    rows: Sequence[dict[str, Any]],
    transform: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Apply the configured mapping to each row, returning new row dicts."""

    validate_transform(transform)
    if not transform:
        return [dict(row) for row in rows]
    transformed: list[dict[str, Any]] = []
    for row in rows:
        result = dict(row)
        for target, spec in transform.items():
            if isinstance(spec, str):
                result[target] = value_at(row, spec)
                continue
            source = str(spec.get("from") or target)
            value = value_at(row, source)
            if value is None and "default" in spec:
                value = spec["default"]
            kind = spec.get("type")
            if value is not None and kind is not None:
                value = _coerce(value, str(kind))
            mask = spec.get("mask")
            if value is not None and mask is not None:
                value = _mask(value, str(mask))
            result[target] = value
        transformed.append(result)
    return transformed


def _dedupe_fields(dedupe_key: str) -> list[str]:
    fields = [field.strip() for field in dedupe_key.split(",") if field.strip()]
    if not fields:
        raise InvalidArgumentError("dedupe_key must name at least one field")
    return fields


def row_hash(row: dict[str, Any], dedupe_key: str) -> str | None:
    """Return a stable hash for the configured key, or None when it is empty."""

    fields = _dedupe_fields(dedupe_key)
    values = [value_at(row, field) for field in fields]
    if all(value is None for value in values):
        return None
    canonical = json.dumps(values, ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def dedupe_rows(
    rows: Sequence[dict[str, Any]],
    dedupe_key: str | None,
    seen: set[str] | None = None,
) -> tuple[list[dict[str, Any]], int]:
    """Drop duplicate rows and return ``(kept_rows, skipped_count)``."""

    if not dedupe_key:
        return list(rows), 0
    seen_hashes = seen if seen is not None else set()
    kept: list[dict[str, Any]] = []
    skipped = 0
    for row in rows:
        digest = row_hash(row, dedupe_key)
        if digest is not None and digest in seen_hashes:
            skipped += 1
            continue
        if digest is not None:
            seen_hashes.add(digest)
        kept.append(row)
    return kept, skipped


__all__ = [
    "apply_transform",
    "dedupe_rows",
    "row_hash",
    "validate_transform",
    "value_at",
]
