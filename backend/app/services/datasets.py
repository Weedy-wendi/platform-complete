"""Dataset read service."""

from __future__ import annotations

from datetime import datetime

from app.services.models import Dataset, DatasetVersion, Sample
from app.services.repositories import DatasetRepository


def _key(dataset: Dataset) -> tuple[str, str]:
    stamp = dataset.updated_at.isoformat() if dataset.updated_at else ""
    return (stamp, dataset.id)


class DatasetService:
    def __init__(self, repository: DatasetRepository) -> None:
        self._repository = repository

    def search_datasets(
        self,
        tenant_id: str,
        *,
        query: str | None = None,
        project_id: str | None = None,
        tags: tuple[str, ...] = (),
        updated_after: datetime | None = None,
    ) -> list[Dataset]:
        needle = query.strip().lower() if query else None
        wanted_tags = set(tags)
        result: list[Dataset] = []
        for dataset in self._repository.list_for_tenant(tenant_id):
            if dataset.tenant_id != tenant_id:
                continue
            if project_id is not None and dataset.project_id != project_id:
                continue
            if needle and needle not in dataset.name.lower():
                continue
            if wanted_tags and not wanted_tags.issubset(set(dataset.tags)):
                continue
            if updated_after is not None and (dataset.updated_at is None or dataset.updated_at < updated_after):
                continue
            result.append(dataset)
        return sorted(result, key=_key, reverse=True)

    def get_schema(self, tenant_id: str, dataset_id: str, version: int | None = None) -> DatasetVersion | None:
        record = self._repository.get_version(tenant_id, dataset_id, version)
        if record is None or record.tenant_id != tenant_id:
            return None
        return record

    def latest_version(self, tenant_id: str, dataset_id: str) -> int | None:
        record = self.get_schema(tenant_id, dataset_id, None)
        return record.version if record else None

    def list_samples(self, tenant_id: str, dataset_id: str, version: int | None = None) -> list[Sample]:
        resolved = version
        if resolved is None:
            resolved = self.latest_version(tenant_id, dataset_id)
        if resolved is None:
            return []
        return [
            sample
            for sample in self._repository.list_samples(tenant_id, dataset_id, resolved)
            if sample.tenant_id == tenant_id
        ]
