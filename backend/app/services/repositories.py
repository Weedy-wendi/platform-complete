"""Repository protocols and in-memory implementations.

The MCP feature reuses the platform's existing application services. In this
repository those services are represented by protocols plus deterministic
in-memory implementations so the MCP layer can be exercised without the full
platform. A SQL-backed implementation would satisfy the same protocols.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from app.services.models import (
    Badcase,
    Dataset,
    DatasetVersion,
    Evaluator,
    Project,
    Run,
    RunItem,
    Sample,
)


class ProjectRepository(Protocol):
    def list_for_tenant(self, tenant_id: str) -> Sequence[Project]: ...


class DatasetRepository(Protocol):
    def list_for_tenant(self, tenant_id: str) -> Sequence[Dataset]: ...

    def get_version(self, tenant_id: str, dataset_id: str, version: int | None) -> DatasetVersion | None: ...

    def list_samples(self, tenant_id: str, dataset_id: str, version: int) -> Sequence[Sample]: ...


class EvaluatorRepository(Protocol):
    def list_for_tenant(self, tenant_id: str, project_id: str | None = None) -> Sequence[Evaluator]: ...


class RunRepository(Protocol):
    def get(self, tenant_id: str, run_id: str) -> Run | None: ...

    def list_items(self, tenant_id: str, run_id: str) -> Sequence[RunItem]: ...


class BadcaseRepository(Protocol):
    def list_for_tenant(self, tenant_id: str) -> Sequence[Badcase]: ...


class InMemoryProjectRepository:
    def __init__(self, projects: Sequence[Project] = ()) -> None:
        self._projects = list(projects)

    def list_for_tenant(self, tenant_id: str) -> Sequence[Project]:
        return [project for project in self._projects if project.tenant_id == tenant_id]


class InMemoryDatasetRepository:
    def __init__(
        self,
        datasets: Sequence[Dataset] = (),
        versions: Sequence[DatasetVersion] = (),
        samples: Sequence[Sample] = (),
    ) -> None:
        self._datasets = list(datasets)
        self._versions = list(versions)
        self._samples = list(samples)

    def list_for_tenant(self, tenant_id: str) -> Sequence[Dataset]:
        return [dataset for dataset in self._datasets if dataset.tenant_id == tenant_id]

    def get_version(self, tenant_id: str, dataset_id: str, version: int | None) -> DatasetVersion | None:
        candidates = [item for item in self._versions if item.tenant_id == tenant_id and item.dataset_id == dataset_id]
        if version is None:
            if not candidates:
                return None
            return max(candidates, key=lambda item: item.version)
        for item in candidates:
            if item.version == version:
                return item
        return None

    def list_samples(self, tenant_id: str, dataset_id: str, version: int) -> Sequence[Sample]:
        return [
            sample
            for sample in self._samples
            if sample.tenant_id == tenant_id and sample.dataset_id == dataset_id and sample.version == version
        ]


class InMemoryEvaluatorRepository:
    def __init__(self, evaluators: Sequence[Evaluator] = ()) -> None:
        self._evaluators = list(evaluators)

    def list_for_tenant(self, tenant_id: str, project_id: str | None = None) -> Sequence[Evaluator]:
        return [
            evaluator
            for evaluator in self._evaluators
            if evaluator.tenant_id == tenant_id
            and evaluator.published
            and (project_id is None or evaluator.project_id in {None, project_id})
        ]


class InMemoryRunRepository:
    def __init__(self, runs: Sequence[Run] = (), items: Sequence[RunItem] = ()) -> None:
        self._runs = list(runs)
        self._items = list(items)

    def get(self, tenant_id: str, run_id: str) -> Run | None:
        for run in self._runs:
            if run.tenant_id == tenant_id and run.id == run_id:
                return run
        return None

    def list_items(self, tenant_id: str, run_id: str) -> Sequence[RunItem]:
        return [item for item in self._items if item.tenant_id == tenant_id and item.run_id == run_id]


class InMemoryBadcaseRepository:
    def __init__(self, badcases: Sequence[Badcase] = ()) -> None:
        self._badcases = list(badcases)

    def list_for_tenant(self, tenant_id: str) -> Sequence[Badcase]:
        return [badcase for badcase in self._badcases if badcase.tenant_id == tenant_id]
