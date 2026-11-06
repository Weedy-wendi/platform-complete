"""Run manifest hashing, validation and budget checks (EVL-05)."""

from __future__ import annotations

from dataclasses import replace

import pytest

from app.core.errors import InvalidArgumentError
from app.modules.evaluation.manifest import (
    build_manifest,
    canonical_json,
    manifest_hash,
    manifest_payload,
    verify_manifest_hash,
)
from app.modules.evaluation.types import SampleInput, StartRunRequest

_HASH = "a" * 64
_EVALUATORS = (
    {
        "id": "ev1",
        "name": "exact",
        "kind": "rule",
        "rule": "exact_match",
        "metric": {"name": "accuracy", "direction": "higher_is_better"},
    },
)
_METRICS = ({"name": "accuracy", "direction": "higher_is_better"},)
_TARGET = {"adapter": "fake", "model": "fake-1", "temperature": 0.0, "seed": 7}


def request(**overrides: object) -> StartRunRequest:
    values: dict[str, object] = {
        "client_request_id": "req-1",
        "dataset_id": "dataset-1",
        "dataset_version": 1,
        "dataset_hash": _HASH,
        "samples": (SampleInput("s1", {"input": "hello"}, expected="hello"),),
        "target_config": dict(_TARGET),
        "evaluator_versions": _EVALUATORS,
        "metric_configs": _METRICS,
        "sampling": {"strategy": "full", "seed": 42},
        "code_version": "abc123",
        "adapter_version": "v1",
        "target_config_version": "cfg-1",
        "env": "test",
    }
    values.update(overrides)
    return StartRunRequest(**values)  # type: ignore[arg-type]


def test_manifest_hash_is_stable_and_ignores_run_id() -> None:
    first = build_manifest("RUN_A", request())
    second = build_manifest("RUN_B", request())
    assert manifest_hash(first) == manifest_hash(second)
    assert verify_manifest_hash(first, manifest_hash(second))
    assert manifest_hash(first) == manifest_hash(build_manifest("RUN_C", request()))


def test_manifest_normalizes_evaluator_and_metric_order() -> None:
    extra = {
        "id": "ev2",
        "name": "contains",
        "kind": "rule",
        "rule": "contains",
        "metric": {"name": "accuracy", "direction": "higher_is_better"},
    }
    left = build_manifest("RUN_A", request(evaluator_versions=(_EVALUATORS[0], extra)))
    right = build_manifest("RUN_B", request(evaluator_versions=(extra, _EVALUATORS[0])))
    assert manifest_hash(left) == manifest_hash(right)
    assert canonical_json(manifest_payload(left)) == canonical_json(manifest_payload(right))


def test_manifest_hash_changes_with_configuration() -> None:
    base = manifest_hash(build_manifest("RUN_A", request()))
    assert base != manifest_hash(build_manifest("RUN_B", request(sampling={"strategy": "full", "seed": 43})))
    assert base != manifest_hash(build_manifest("RUN_B", request(code_version="def456")))
    assert base != manifest_hash(build_manifest("RUN_B", request(mode="replay")))


def test_manifest_rejects_missing_or_invalid_fields() -> None:
    with pytest.raises(InvalidArgumentError):
        build_manifest("RUN_A", request(dataset_hash=""))
    with pytest.raises(InvalidArgumentError):
        build_manifest("RUN_A", request(evaluator_versions=()))
    with pytest.raises(InvalidArgumentError):
        build_manifest("RUN_A", request(sampling={"strategy": "full"}))
    with pytest.raises(InvalidArgumentError):
        build_manifest("RUN_A", request(target_config={}))
    with pytest.raises(InvalidArgumentError):
        build_manifest("RUN_A", request(code_version=""))
    with pytest.raises(InvalidArgumentError):
        build_manifest("RUN_A", request(env=""))
    with pytest.raises(InvalidArgumentError):
        build_manifest("RUN_A", request(mode="invalid"))  # type: ignore[arg-type]


def test_manifest_rejects_duplicate_samples_and_budget_overrun() -> None:
    from app.modules.evaluation.manifest import validate_start_request

    with pytest.raises(InvalidArgumentError):
        validate_start_request(request(samples=(SampleInput("same", {}), SampleInput("same", {}))))
    with pytest.raises(InvalidArgumentError):
        validate_start_request(request(budget_usd=1.0, estimated_cost_usd=2.0))
    validate_start_request(request(budget_usd=2.0, estimated_cost_usd=1.0))


def test_manifest_payload_does_not_mutate_source_lists() -> None:
    manifest = build_manifest("RUN_A", request())
    payload = manifest_payload(manifest)
    payload["evaluator_versions"].clear()
    assert manifest.evaluator_versions
    assert replace(manifest, run_id="RUN_B").run_id == "RUN_B"
