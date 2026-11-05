"""Immutable catalog DTOs."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class SchemaField:
    name: str
    type: str
    nullable: bool = True
    description: str | None = None


@dataclass(frozen=True)
class ProjectView:
    id: str
    tenant_id: str
    name: str
    description: str


@dataclass(frozen=True)
class DatasourceView:
    id: str
    tenant_id: str
    project_id: str
    name: str
    kind: str
    secret_ref: str | None


@dataclass(frozen=True)
class DatasetView:
    id: str
    tenant_id: str
    project_id: str
    name: str
    latest_version: int
    sample_count: int
    tags: tuple[str, ...] = ()


@dataclass(frozen=True)
class DatasetVersionRef:
    tenant_id: str
    dataset_id: str
    version: int
    content_hash: str


@dataclass(frozen=True)
class DatasetVersionView:
    ref: DatasetVersionRef
    row_count: int
    fields: tuple[SchemaField, ...] = ()


@dataclass(frozen=True)
class SampleView:
    id: str
    sample_key: str
    payload: dict = field(default_factory=dict)
    artifact_id: str | None = None
