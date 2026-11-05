"""Adapters from module ``public`` services to REST ports.

Only classes exported from ``app.modules.catalog.public`` are referenced here;
ORM models and internal repositories stay private to the module.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from app.api.errors import unprocessable_error
from app.api.ports import (
    DatasetRecord,
    DatasetVersionRecord,
    ProjectRecord,
    ReportRecord,
    SampleRecord,
    ShareLinkRecord,
)
from app.core.context import TenantContext
from app.core.errors import NotFoundError, ServiceUnavailableError
from app.core.pagination import Page
from app.modules.catalog.public import (
    CatalogReader,
    CatalogService,
    DatasetQuery,
    DatasetVersionRef,
    DatasetVersionView,
    DatasetView,
    ProjectView,
    SampleView,
    SchemaField,
)
from app.modules.reporting.public import ReportService, RunReport

Catalog = CatalogReader | CatalogService


def _project_record(view: ProjectView) -> ProjectRecord:
    return ProjectRecord(
        id=view.id,
        name=view.name,
        description=view.description or None,
    )


def _dataset_record(view: DatasetView) -> DatasetRecord:
    return DatasetRecord(
        id=view.id,
        project_id=view.project_id,
        name=view.name,
        latest_version=view.latest_version,
        sample_count=view.sample_count,
        tags=tuple(view.tags),
    )


def _version_record(view: DatasetVersionView) -> DatasetVersionRecord:
    return DatasetVersionRecord(
        dataset_id=view.ref.dataset_id,
        version=view.ref.version,
        content_hash=view.ref.content_hash,
        row_count=view.row_count,
        schema={"fields": [field.__dict__ for field in view.fields]},
    )


def _sample_record(view: SampleView) -> SampleRecord:
    return SampleRecord(sample_id=view.sample_key or view.id, payload=dict(view.payload or {}))


def _write_method(catalog: Catalog, name: str):
    method = getattr(catalog, name, None)
    if not callable(method):
        raise ServiceUnavailableError(f"Catalog write service is not configured ({name})")
    return method


class CatalogProjectsAdapter:
    def __init__(self, catalog: Catalog) -> None:
        self._catalog = catalog

    def list_projects(self, ctx: TenantContext, *, cursor: str | None, limit: int) -> Page[ProjectRecord]:
        page = self._catalog.list_projects(ctx, cursor, limit)
        return Page(
            items=[_project_record(view) for view in page.items],
            next_cursor=page.next_cursor,
            truncated=page.truncated,
        )

    def create_project(
        self,
        ctx: TenantContext,
        *,
        name: str,
        description: str | None = None,
        idempotency_key: str | None = None,
    ) -> ProjectRecord:
        _ = idempotency_key
        view = _write_method(self._catalog, "create_project")(ctx, name, description or "")
        return _project_record(view)

    def get_project(self, ctx: TenantContext, project_id: str) -> ProjectRecord:
        cursor: str | None = None
        for _ in range(10):
            page = self._catalog.list_projects(ctx, cursor, 100)
            for view in page.items:
                if view.id == project_id:
                    return _project_record(view)
            if not page.next_cursor:
                break
            cursor = page.next_cursor
        raise NotFoundError("Project not found")

    def update_project(
        self,
        ctx: TenantContext,
        project_id: str,
        *,
        name: str | None = None,
        description: str | None = None,
    ) -> ProjectRecord:
        view = _write_method(self._catalog, "update_project")(
            ctx,
            project_id,
            name=name,
            description=description,
        )
        return _project_record(view)

    def delete_project(self, ctx: TenantContext, project_id: str) -> None:
        _write_method(self._catalog, "delete_project")(ctx, project_id)


class CatalogDatasetsAdapter:
    def __init__(self, catalog: Catalog) -> None:
        self._catalog = catalog

    def search_datasets(
        self,
        ctx: TenantContext,
        *,
        query: str | None = None,
        project_id: str | None = None,
        tags: tuple[str, ...] = (),
        cursor: str | None = None,
        limit: int = 20,
    ) -> Page[DatasetRecord]:
        page = self._catalog.search_datasets(
            ctx,
            DatasetQuery(query=query, project_id=project_id, tags=tags),
            cursor,
            limit,
        )
        return Page(
            items=[_dataset_record(view) for view in page.items],
            next_cursor=page.next_cursor,
            truncated=page.truncated,
        )

    def create_dataset(
        self,
        ctx: TenantContext,
        *,
        project_id: str,
        name: str,
        tags: tuple[str, ...] = (),
        idempotency_key: str | None = None,
    ) -> DatasetRecord:
        _ = idempotency_key
        view = _write_method(self._catalog, "create_dataset")(
            ctx,
            project_id=project_id,
            name=name,
            tags=tags,
        )
        return _dataset_record(view)

    def publish_version(
        self,
        ctx: TenantContext,
        dataset_id: str,
        *,
        schema: dict[str, Any],
        content_hash: str,
        samples: Sequence[dict[str, Any]] = (),
        idempotency_key: str | None = None,
    ) -> DatasetVersionRecord:
        _ = idempotency_key
        fields = tuple(
            SchemaField(
                name=str(item.get("name")),
                type=str(item.get("type", "string")),
                nullable=bool(item.get("nullable", True)),
                description=item.get("description"),
            )
            for item in schema.get("fields", [])
            if item.get("name")
        )
        ref = _write_method(self._catalog, "publish_version")(
            ctx,
            dataset_id,
            list(samples),
            schema_fields=fields,
        )
        if content_hash and ref.content_hash != content_hash:
            raise unprocessable_error(
                "content_hash does not match the published content",
                expected=content_hash,
                actual=ref.content_hash,
            )
        view = self._catalog.get_version(ctx, ref)
        return _version_record(view)

    def page_samples(
        self,
        ctx: TenantContext,
        dataset_id: str,
        version: int,
        *,
        cursor: str | None = None,
        limit: int = 20,
    ) -> Page[SampleRecord]:
        page = self._catalog.page_samples(
            ctx,
            DatasetVersionRef(ctx.tenant_id, dataset_id, version, ""),
            cursor,
            limit,
        )
        return Page(
            items=[_sample_record(view) for view in page.items],
            next_cursor=page.next_cursor,
            truncated=page.truncated,
        )


class ReportingReportsAdapter:
    """Adapts the reporting module's public service to :class:`ReportsPort`."""

    def __init__(self, service: ReportService) -> None:
        self._service = service

    def get_report(self, ctx: TenantContext, run_id: str, fmt: str) -> ReportRecord:
        report = self._service.get_run_report(ctx, run_id, fmt)
        return _report_record(report)

    def create_share_link(
        self,
        ctx: TenantContext,
        run_id: str,
        *,
        secret: str,
        ttl_seconds: int = 3600,
    ) -> ShareLinkRecord:
        token = self._service.create_share_link(
            ctx,
            run_id,
            secret=secret,
            fmt="json",
            ttl_seconds=ttl_seconds,
        )
        target = self._service.read_share_link(token, secret=secret)
        return ShareLinkRecord(
            token=token,
            expires_at=datetime.fromtimestamp(target.expires_at, tz=UTC),
        )

    def resolve_share_link(self, ctx: TenantContext, token: str, *, secret: str) -> ReportRecord:
        target = self._service.resolve_share_link(ctx, token, secret=secret)
        report = self._service.get_run_report(ctx, target.run_id, "json")
        return _report_record(report)


def _report_record(report: RunReport) -> ReportRecord:
    media_type = "application/json" if report.format == "json" else "text/markdown; charset=utf-8"
    return ReportRecord(
        run_id=report.run_id,
        manifest_hash=report.manifest_hash,
        format=report.format,
        content=report.content,
        media_type=media_type,
    )


__all__ = ["CatalogDatasetsAdapter", "CatalogProjectsAdapter", "ReportingReportsAdapter"]
