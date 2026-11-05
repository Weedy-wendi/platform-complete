"""Catalog service integration tests (CAT-01..06)."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine

from app.core.context import TenantContext
from app.core.db import Base, make_session_factory
from app.core.errors import InvalidArgumentError, NotFoundError
from app.modules.catalog.models import (
    Dataset,
    DatasetVersion,
    Datasource,
    LineageEdge,
    Project,
    Sample,
)
from app.modules.catalog.service import CatalogService, DatasetQuery
from app.modules.catalog.views import SchemaField

_TABLES = [
    Project.__table__,
    Datasource.__table__,
    Dataset.__table__,
    DatasetVersion.__table__,
    Sample.__table__,
    LineageEdge.__table__,
]


@pytest.fixture()
def factory():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine, tables=_TABLES)
    try:
        yield make_session_factory(engine)
    finally:
        engine.dispose()


@pytest.fixture()
def service(factory) -> CatalogService:
    return CatalogService(factory)


@pytest.fixture()
def ctx() -> TenantContext:
    return TenantContext(tenant_id="tenant-a", subject_id="user:1", scopes=frozenset(), trace_id="trace-1")


def _setup(service: CatalogService, ctx: TenantContext) -> tuple[str, str]:
    project = service.create_project(ctx, "Project", "desc")
    dataset = service.create_dataset(ctx, project_id=project.id, name="Dataset", tags=("demo",))
    return project.id, dataset.id


def test_project_crud_and_unique_name(service: CatalogService, ctx: TenantContext) -> None:
    project = service.create_project(ctx, "Alpha")
    assert service.list_projects(ctx).items[0].name == "Alpha"
    with pytest.raises(InvalidArgumentError):
        service.create_project(ctx, "Alpha")
    service.delete_project(ctx, project.id)
    assert service.list_projects(ctx).items == []
    with pytest.raises(NotFoundError):
        service.delete_project(ctx, project.id)


def test_datasource_rejects_plaintext_secrets(service: CatalogService, ctx: TenantContext) -> None:
    project_id, _ = _setup(service, ctx)
    source = service.create_datasource(
        ctx,
        project_id=project_id,
        name="mysql",
        kind="mysql",
        secret_ref="secret://tenant-a/mysql",
        config={"host": "db", "database": "pingce"},
    )
    assert source.secret_ref == "secret://tenant-a/mysql"
    assert service.test_datasource(ctx, source.id) is True
    with pytest.raises(InvalidArgumentError):
        service.create_datasource(ctx, project_id=project_id, name="bad", kind="mysql", config={"password": "x"})
    with pytest.raises(InvalidArgumentError):
        service.create_datasource(ctx, project_id=project_id, name="bad2", kind="mysql", config={"host": "db"})


def test_update_project(service: CatalogService, ctx: TenantContext) -> None:
    project = service.create_project(ctx, "Before")
    updated = service.update_project(ctx, project.id, name="After", description="changed")
    assert updated.name == "After"
    assert updated.description == "changed"


def test_publish_is_immutable_and_deduplicates_content(service: CatalogService, ctx: TenantContext) -> None:
    _, dataset_id = _setup(service, ctx)
    samples = [
        {"sample_key": "1", "payload": {"q": "a", "a": "b"}},
        {"sample_key": "2", "payload": {"q": "c", "a": "d"}},
    ]
    first = service.publish_version(
        ctx,
        dataset_id,
        samples,
        schema_fields=[SchemaField("q", "string"), SchemaField("a", "string")],
    )
    assert first.version == 1

    duplicate = service.publish_version(ctx, dataset_id, list(reversed(samples)))
    assert duplicate.version == 1
    assert duplicate.content_hash == first.content_hash

    second = service.publish_version(ctx, dataset_id, [{"sample_key": "1", "payload": {"q": "new"}}])
    assert second.version == 2

    version = service.get_version(ctx, first)
    assert version.row_count == 2
    assert version.fields[0].name == "q"


def test_bulk_samples_deduplicate_and_row_count(service: CatalogService, ctx: TenantContext) -> None:
    _, dataset_id = _setup(service, ctx)
    samples = [
        {"sample_key": "1", "payload": {"q": "a"}},
        {"sample_key": "1", "payload": {"q": "duplicate"}},
        {"sample_key": "2", "payload": {"q": "b"}},
    ]
    ref = service.publish_version(ctx, dataset_id, samples)
    page = service.page_samples(ctx, ref, limit=1)
    assert page.truncated is False or page.next_cursor is not None
    assert [item.sample_key for item in page.items] == ["1"]
    second = service.page_samples(ctx, ref, cursor=page.next_cursor, limit=10)
    assert [item.sample_key for item in second.items] == ["2"]
    assert service.get_version(ctx, ref).row_count == 2


def test_reader_search_and_lineage(service: CatalogService, ctx: TenantContext) -> None:
    project_id, dataset_id = _setup(service, ctx)
    service.create_dataset(ctx, project_id=project_id, name="Other")
    page = service.search_datasets(ctx, DatasetQuery(query="data"))
    assert [item.name for item in page.items] == ["Dataset"]
    tagged = service.search_datasets(ctx, DatasetQuery(tags=("demo",)))
    assert [item.name for item in tagged.items] == ["Dataset"]

    service.add_lineage(
        ctx,
        upstream_type="dataset",
        upstream_id=dataset_id,
        downstream_type="run",
        downstream_id="run-1",
    )
    edges = service.trace_lineage(ctx, node_type="dataset", node_id=dataset_id)
    assert len(edges) == 1
    assert edges[0].downstream_id == "run-1"


def test_schema_validation_rejects_missing_and_extra_fields(service: CatalogService, ctx: TenantContext) -> None:
    _, dataset_id = _setup(service, ctx)
    fields = [SchemaField("q", "string", nullable=False)]
    with pytest.raises(InvalidArgumentError):
        service.publish_version(ctx, dataset_id, [{"sample_key": "1", "payload": {"a": "b"}}], schema_fields=fields)
    with pytest.raises(InvalidArgumentError):
        service.publish_version(
            ctx,
            dataset_id,
            [{"sample_key": "1", "payload": {"q": "a", "extra": "x"}}],
            schema_fields=fields,
        )


def test_cross_tenant_version_is_not_found(service: CatalogService, ctx: TenantContext) -> None:
    _, dataset_id = _setup(service, ctx)
    ref = service.publish_version(ctx, dataset_id, [{"sample_key": "1", "payload": {"q": "a"}}])
    other = TenantContext(tenant_id="tenant-b", subject_id="user:2", scopes=frozenset(), trace_id="trace-2")
    with pytest.raises(NotFoundError):
        service.get_version(other, ref)
    with pytest.raises(NotFoundError):
        service.get_schema(other, dataset_id)
