"""Project read service."""

from __future__ import annotations

from app.services.models import Project
from app.services.repositories import ProjectRepository


def _key(project: Project) -> tuple[str, str]:
    stamp = project.updated_at.isoformat() if project.updated_at else ""
    return (stamp, project.id)


class ProjectService:
    def __init__(self, repository: ProjectRepository) -> None:
        self._repository = repository

    def list_projects(self, tenant_id: str) -> list[Project]:
        records = [item for item in self._repository.list_for_tenant(tenant_id) if item.tenant_id == tenant_id]
        return sorted(records, key=_key, reverse=True)
