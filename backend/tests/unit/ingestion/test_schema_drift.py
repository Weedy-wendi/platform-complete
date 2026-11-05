"""Schema inference and drift tests (ING-05)."""

from __future__ import annotations

from app.modules.ingestion.public import ConnectorField
from app.modules.ingestion.schema import detect_drift, infer_schema, schema_to_records


def test_infer_schema_types_and_nullability() -> None:
    fields = infer_schema(
        [
            {"id": 1, "score": 1.5, "ok": True, "name": "a", "meta": {"x": 1}, "missing": None},
            {"id": 2, "score": 2, "ok": False, "name": "b", "meta": {"x": 2}},
        ]
    )
    by_name = {field.name: field for field in fields}
    assert by_name["id"].data_type == "integer"
    assert by_name["score"].data_type == "number"
    assert by_name["ok"].data_type == "boolean"
    assert by_name["name"].data_type == "string"
    assert by_name["meta"].data_type == "object"
    assert by_name["missing"].nullable is True


def test_infer_schema_mixed_types_becomes_string() -> None:
    fields = infer_schema([{"value": 1}, {"value": "two"}])
    assert fields[0].data_type == "string"


def test_detect_drift_added_removed_and_changed() -> None:
    previous = [
        ConnectorField("id", "integer"),
        ConnectorField("name", "string"),
        ConnectorField("legacy", "string"),
    ]
    current = [
        ConnectorField("id", "string"),
        ConnectorField("name", "string"),
        ConnectorField("email", "string"),
    ]
    drift = detect_drift(previous, current)
    assert drift.has_drift is True
    assert drift.added == ("email",)
    assert drift.removed == ("legacy",)
    assert drift.changed == (("id", "integer", "string"),)
    kinds = {alert["kind"] for alert in drift.alerts()}
    assert kinds == {"field_added", "field_removed", "field_type_changed"}


def test_detect_drift_accepts_serialized_fields() -> None:
    previous = schema_to_records([ConnectorField("id", "integer")])
    drift = detect_drift(previous, [ConnectorField("id", "integer")])
    assert drift.has_drift is False
