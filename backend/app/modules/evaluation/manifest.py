"""Run manifest construction, canonicalization and stable hashing.

The manifest hash deliberately excludes ``run_id``: two runs created with the
same configuration share a hash even though they have different ids. This is
what makes replay and comparison meaningful.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from typing import Any

from app.core.errors import InvalidArgumentError
from app.modules.evaluation.types import RunManifest, StartRunRequest

_CONFIG_FIELDS = (
    "dataset_hash",
    "evaluator_versions",
    "metric_configs",
    "target_config",
    "sampling",
    "code_version",
    "adapter_version",
    "target_config_version",
    "mode",
    "env",
)


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def _normalize(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _normalize(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_normalize(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def normalized_evaluator_versions(versions: list[dict[str, Any]] | tuple[dict[str, Any], ...]) -> list[dict[str, Any]]:
    """Return a deterministic representation of evaluator version references.

    Ordering is normalized because the hash describes the scoring plan, not the
    insertion order of a JSON array.
    """

    normalized = [_normalize(dict(item)) for item in versions]
    return sorted(normalized, key=canonical_json)


def normalized_metric_configs(configs: list[dict[str, Any]] | tuple[dict[str, Any], ...]) -> list[dict[str, Any]]:
    normalized = [_normalize(dict(item)) for item in configs]
    return sorted(normalized, key=canonical_json)


def manifest_payload(manifest: RunManifest, *, include_run_id: bool = False) -> dict[str, Any]:
    payload: dict[str, Any] = {field: _normalize(getattr(manifest, field)) for field in _CONFIG_FIELDS}
    payload["evaluator_versions"] = normalized_evaluator_versions(payload["evaluator_versions"])
    payload["metric_configs"] = normalized_metric_configs(payload["metric_configs"])
    if include_run_id:
        payload["run_id"] = manifest.run_id
    return payload


def manifest_hash(manifest: RunManifest) -> str:
    return hashlib.sha256(canonical_json(manifest_payload(manifest)).encode("utf-8")).hexdigest()


def verify_manifest_hash(manifest: RunManifest, expected_hash: str) -> bool:
    return manifest_hash(manifest) == expected_hash


def validate_manifest(manifest: RunManifest) -> None:
    if not manifest.run_id.strip():
        raise InvalidArgumentError("manifest run_id is required")
    if not manifest.dataset_hash.strip():
        raise InvalidArgumentError("manifest dataset_hash is required")
    if not manifest.evaluator_versions:
        raise InvalidArgumentError("manifest evaluator_versions is required")
    for index, version in enumerate(manifest.evaluator_versions):
        if not isinstance(version, dict) or not version:
            raise InvalidArgumentError("evaluator_versions entries must be non-empty objects", index=index)
    for index, config in enumerate(manifest.metric_configs):
        if not isinstance(config, dict) or not config:
            raise InvalidArgumentError("metric_configs entries must be non-empty objects", index=index)
    if not isinstance(manifest.target_config, dict) or not manifest.target_config:
        raise InvalidArgumentError("manifest target_config is required")
    if not isinstance(manifest.sampling, dict) or "seed" not in manifest.sampling:
        raise InvalidArgumentError("manifest sampling.seed is required")
    if not str(manifest.sampling.get("strategy") or "").strip():
        raise InvalidArgumentError("manifest sampling.strategy is required")
    if not manifest.code_version.strip():
        raise InvalidArgumentError("manifest code_version is required")
    if not manifest.env.strip():
        raise InvalidArgumentError("manifest env is required")
    if manifest.mode not in {"record", "replay"}:
        raise InvalidArgumentError("manifest mode must be record or replay", mode=manifest.mode)
    if not manifest.adapter_version.strip():
        raise InvalidArgumentError("manifest adapter_version is required")
    if not manifest.target_config_version.strip():
        raise InvalidArgumentError("manifest target_config_version is required")


def validate_start_request(request: StartRunRequest) -> None:
    if not request.client_request_id.strip():
        raise InvalidArgumentError("client_request_id is required")
    if not request.samples:
        raise InvalidArgumentError("at least one sample is required")
    keys = [sample.sample_key.strip() for sample in request.samples]
    if any(not key for key in keys):
        raise InvalidArgumentError("sample_key is required")
    if len(set(keys)) != len(keys):
        raise InvalidArgumentError("sample keys must be unique")
    if request.budget_usd is not None and request.budget_usd < 0:
        raise InvalidArgumentError("budget_usd must be non-negative")
    if request.estimated_cost_usd < 0:
        raise InvalidArgumentError("estimated_cost_usd must be non-negative")
    if request.budget_usd is not None and request.estimated_cost_usd > request.budget_usd:
        raise InvalidArgumentError(
            "estimated cost exceeds the run budget",
            budget_usd=request.budget_usd,
            estimated_cost_usd=request.estimated_cost_usd,
        )
    if request.mode not in {"record", "replay"}:
        raise InvalidArgumentError("mode must be record or replay", mode=request.mode)


def build_manifest(run_id: str, request: StartRunRequest) -> RunManifest:
    manifest = RunManifest(
        run_id=run_id,
        dataset_hash=request.dataset_hash,
        evaluator_versions=[dict(item) for item in request.evaluator_versions],
        metric_configs=[dict(item) for item in request.metric_configs],
        target_config=dict(request.target_config),
        sampling=dict(request.sampling),
        code_version=request.code_version,
        adapter_version=request.adapter_version,
        target_config_version=request.target_config_version,
        mode=request.mode,
        env=request.env,
    )
    validate_manifest(manifest)
    return manifest


def manifest_to_dict(manifest: RunManifest) -> dict[str, Any]:
    payload = asdict(manifest)
    payload["evaluator_versions"] = [dict(item) for item in manifest.evaluator_versions]
    payload["metric_configs"] = [dict(item) for item in manifest.metric_configs]
    return payload
