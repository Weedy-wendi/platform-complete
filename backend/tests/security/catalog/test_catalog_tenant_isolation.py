"""Cross-tenant catalog isolation (CAT-07)."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine

from app.core.context import TenantContext
from app.core.db import Base, make_session_factory
from app.core.errors import NotFoundError
from app.modules.catalog.models import Dataset, DatasetVersion, LineageEdge, Project, Sample
from app.modules.catalog.service import CatalogService

_TABLES = [
    Project.__table__,
    Dataset.__table__,
    DatasetVersion.__table__,
    Sample.__table__,
    LineageEdge.__table__,
]


@pytest.fixture()
def service():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine, tables=_TABLES)
    try:
        yield CatalogService(make_session_factory(engine))
    finally:
        engine.dispose()


def _ctx(tenant: str) -> TenantContext:
    return TenantContext(tenant_id=tenant, subject_id="user:1", scopes=frozenset(), trace_id="trace")


def test_cross_tenant_dataset_is_not_visible(service: CatalogService) -> None:
    project = service.create_project(_ctx("tenant-a"), "Alpha")
    dataset = service.create_dataset(_ctx("tenant-a"), project_id=project.id, name="Dataset")
    ref = service.publish_version(_ctx("tenant-a"), dataset.id, [{"sample_key": "1", "payload": {"q": "a"}}])

    with pytest.raises(NotFoundError):
        service.get_version(_ctx("tenant-b"), ref)
    with pytest.raises(NotFoundError):
        service.get_schema(_ctx("tenant-b"), dataset.id)
    assert service.search_datasets(_ctx("tenant-b")).items == []
    assert service.page_samples(_ctx("tenant-b"), ref).items == []
