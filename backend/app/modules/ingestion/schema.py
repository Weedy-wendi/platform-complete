"""Schema inference and drift detection (ING-05)."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from app.modules.ingestion.public import ConnectorField, SchemaDrift


def infer_value_type(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, (dict, list, tuple)):
        return "object"
    return "string"


def _merge_type(current: str | None, candidate: str) -> str | None:
    if candidate == "null":
        return current
    if current is None or current == "null":
        return candidate
    if current == candidate:
        return current
    if {current, candidate} == {"integer", "number"}:
        return "number"
    return "string"


def infer_schema(rows: Sequence[dict[str, Any]]) -> list[ConnectorField]:
    """Infer a stable, ordered schema from a batch of rows."""

    order: list[str] = []
    types: dict[str, str | None] = {}
    nullable: dict[str, bool] = {}
    for row in rows:
        for name, value in row.items():
            if name not in types:
                order.append(name)
                types[name] = None
                nullable[name] = False
            merged = _merge_type(types[name], infer_value_type(value))
            types[name] = merged
            if value is None:
                nullable[name] = True
    return [
        ConnectorField(
            name=name,
            data_type=types[name] or "null",
            nullable=nullable[name],
        )
        for name in order
    ]


def _as_fields(schema: Sequence[ConnectorField] | Sequence[dict[str, Any]]) -> list[ConnectorField]:
    fields: list[ConnectorField] = []
    for item in schema:
        if isinstance(item, ConnectorField):
            fields.append(item)
        else:
            fields.append(
                ConnectorField(
                    name=str(item.get("name", "")),
                    data_type=str(item.get("data_type", "string")),
                    nullable=bool(item.get("nullable", True)),
                )
            )
    return [field for field in fields if field.name]


def detect_drift(
    previous: Sequence[ConnectorField] | Sequence[dict[str, Any]],
    current: Sequence[ConnectorField] | Sequence[dict[str, Any]],
) -> SchemaDrift:
    """Report new, removed and type-changed fields.

    Nullability changes are reported through ``alerts`` details as well; they
    do not change the field identity, so they are kept as a type-level change
    only when the data type itself changes.
    """

    old_fields = {field.name: field for field in _as_fields(previous)}
    new_fields = {field.name: field for field in _as_fields(current)}
    added = tuple(name for name in new_fields if name not in old_fields)
    removed = tuple(name for name in old_fields if name not in new_fields)
    changed = tuple(
        (name, old_fields[name].data_type, new_fields[name].data_type)
        for name in new_fields
        if name in old_fields and old_fields[name].data_type != new_fields[name].data_type
    )
    return SchemaDrift(added=added, removed=removed, changed=changed)


def schema_to_records(fields: Sequence[ConnectorField]) -> list[dict[str, Any]]:
    return [{"name": field.name, "data_type": field.data_type, "nullable": field.nullable} for field in fields]
