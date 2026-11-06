"""Catalog use cases and read model.

Dataset versions are immutable: publishing always creates a new version, and
the MySQL migration adds a trigger that rejects UPDATE on dataset_version.
"""

from __future__ import annotations

import base64
import hashlib
import json
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from sqlalchemy import and_, func, insert, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.core.clock import utcnow_naive
from app.core.context import TenantContext
from app.core.errors import InvalidArgumentError, NotFoundError
from app.core.ids import new_ulid
from app.core.pagination import Page, clamp_limit
from app.core.repository import TenantScopedRepository
from app.modules.catalog.models import (
    Dataset,
    DatasetVersion,
    Datasource,
    LineageEdge,
    Project,
    Sample,
)
from app.modules.catalog.views import (
    DatasetVersionRef,
    DatasetVersionView,
    DatasetView,
    DatasourceView,
    ProjectView,
    SampleView,
    SchemaField,
)

_MAX_PAYLOAD_BYTES = 1024 * 1024


def canonical_payload(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def content_hash(samples: Iterable[dict[str, Any]]) -> str:
    digest = hashlib.sha256()
    for key, payload in sorted((str(sample["sample_key"]), canonical_payload(sample["payload"])) for sample in samples):
        digest.update(key.encode("utf-8"))
        digest.update(b"\x00")
        digest.update(payload.encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def _normalize_samples(samples: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: dict[str, dict[str, Any]] = {}
    for sample in samples:
        key = str(sample.get("sample_key") or sample.get("id") or "").strip()
        if not key:
            raise InvalidArgumentError("sample_key is required")
        payload = sample.get("payload", sample)
        if len(canonical_payload(payload).encode("utf-8")) > _MAX_PAYLOAD_BYTES and not sample.get("artifact_id"):
            raise InvalidArgumentError("sample payload exceeds 1MB; use artifact_id", sample_key=key)
        normalized[key] = {
            "sample_key": key,
            "payload": payload,
            "artifact_id": sample.get("artifact_id"),
        }
    return list(normalized.values())


def _validate_schema(samples: Sequence[dict[str, Any]], fields: Sequence[SchemaField]) -> None:
    if not fields:
        return
    required = {field.name for field in fields if not field.nullable}
    allowed = {field.name for field in fields}
    for sample in samples:
        payload = sample["payload"]
        if not isinstance(payload, dict):
            raise InvalidArgumentError("sample payload must be an object", sample_key=sample["sample_key"])
        missing = required - set(payload)
        extra = set(payload) - allowed
        if missing:
            raise InvalidArgumentError(
                "sample is missing required fields",
                sample_key=sample["sample_key"],
                missing=sorted(missing),
            )
        if extra:
            raise InvalidArgumentError(
                "sample has fields outside the schema",
                sample_key=sample["sample_key"],
                extra=sorted(extra),
            )


def _encode_cursor(payload: dict[str, Any]) -> str:
    return base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode()


def _decode_cursor(cursor: str) -> dict[str, Any]:
    try:
        return json.loads(base64.urlsafe_b64decode(cursor.encode()))
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        raise InvalidArgumentError("invalid catalog cursor") from exc


@dataclass(frozen=True)
class DatasetQuery:
    query: str | None = None
    project_id: str | None = None
    tags: tuple[str, ...] = ()


class CatalogReader(Protocol):
    def list_projects(self, ctx: TenantContext, cursor: str | None = None, limit: int = 20) -> Page[ProjectView]: ...
    def search_datasets(
        self, ctx: TenantContext, query: DatasetQuery | None = None, cursor: str | None = None, limit: int = 20
    ) -> Page[DatasetView]: ...
    def get_version(self, ctx: TenantContext, ref: DatasetVersionRef) -> DatasetVersionView: ...
    def page_samples(
        self, ctx: TenantContext, ref: DatasetVersionRef, cursor: str | None = None, limit: int = 20
    ) -> Page[SampleView]: ...


class CatalogService:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    # Projects --------------------------------------------------------------

    def create_project(self, ctx: TenantContext, name: str, description: str = "") -> ProjectView:
        if not name.strip():
            raise InvalidArgumentError("project name is required")
        with self._session_factory() as session:
            exists = session.scalar(
                select(Project).where(Project.tenant_id == ctx.tenant_id, Project.name == name.strip())
            )
            if exists is not None:
                raise InvalidArgumentError("project already exists", name=name)
            project = Project(
                id=new_ulid(),
                tenant_id=ctx.tenant_id,
                name=name.strip(),
                description=description,
                created_by=ctx.subject_id,
            )
            session.add(project)
            session.commit()
            return _project_view(project)

    def delete_project(self, ctx: TenantContext, project_id: str) -> None:
        with self._session_factory() as session:
            project = TenantScopedRepository(session, ctx.tenant_id).get(Project, project_id)
            if project is None or project.deleted_at is not None:
                raise NotFoundError("Project not found")
            project.deleted_at = utcnow_naive()
            session.commit()

    def update_project(
        self,
        ctx: TenantContext,
        project_id: str,
        *,
        name: str | None = None,
        description: str | None = None,
    ) -> ProjectView:
        with self._session_factory() as session:
            project = TenantScopedRepository(session, ctx.tenant_id).get(Project, project_id)
            if project is None or project.deleted_at is not None:
                raise NotFoundError("Project not found")
            if name is not None:
                candidate = name.strip()
                if not candidate:
                    raise InvalidArgumentError("project name is required")
                duplicate = session.scalar(
                    select(Project).where(
                        Project.tenant_id == ctx.tenant_id,
                        Project.name == candidate,
                        Project.id != project_id,
                    )
                )
                if duplicate is not None:
                    raise InvalidArgumentError("project already exists", name=candidate)
                project.name = candidate
            if description is not None:
                project.description = description
            project.updated_at = utcnow_naive()
            session.commit()
            return _project_view(project)

    def list_projects(
        self,
        ctx: TenantContext,
        cursor: str | None = None,
        limit: int = 20,
    ) -> Page[ProjectView]:
        page_size = clamp_limit(limit, default=20, maximum=100)
        statement = select(Project).where(
            Project.tenant_id == ctx.tenant_id,
            Project.deleted_at.is_(None),
        )
        if cursor:
            payload = _decode_cursor(cursor)
            stamp = datetime.fromisoformat(payload["t"])
            statement = statement.where(
                or_(
                    Project.updated_at < stamp,
                    and_(Project.updated_at == stamp, Project.id < payload["id"]),
                )
            )
        statement = statement.order_by(Project.updated_at.desc(), Project.id.desc()).limit(page_size + 1)
        with self._session_factory() as session:
            rows = list(session.scalars(statement))
        items = rows[:page_size]
        next_cursor = (
            _encode_cursor({"t": items[-1].updated_at.isoformat(), "id": items[-1].id})
            if len(rows) > page_size and items
            else None
        )
        return Page(
            items=[_project_view(row) for row in items],
            next_cursor=next_cursor,
            truncated=len(rows) > page_size,
        )

    # Datasources -----------------------------------------------------------

    def create_datasource(
        self,
        ctx: TenantContext,
        *,
        project_id: str,
        name: str,
        kind: str,
        secret_ref: str | None = None,
        config: dict[str, Any] | None = None,
    ) -> DatasourceView:
        _reject_plaintext_secrets(config or {})
        with self._session_factory() as session:
            project = TenantScopedRepository(session, ctx.tenant_id).get(Project, project_id)
            if project is None or project.deleted_at is not None:
                raise NotFoundError("Project not found")
            self._validate_datasource(kind, config or {}, secret_ref)
            datasource = Datasource(
                id=new_ulid(),
                tenant_id=ctx.tenant_id,
                project_id=project_id,
                name=name,
                kind=kind,
                secret_ref=secret_ref,
                config=config or {},
                created_by=ctx.subject_id,
            )
            session.add(datasource)
            session.commit()
            return DatasourceView(
                id=datasource.id,
                tenant_id=datasource.tenant_id,
                project_id=datasource.project_id,
                name=datasource.name,
                kind=datasource.kind,
                secret_ref=datasource.secret_ref,
            )

    # Datasets / versions ---------------------------------------------------

    def test_datasource(self, ctx: TenantContext, datasource_id: str) -> bool:
        """Validate the stored connection descriptor.

        Actual network connectors live in the ingestion module; the catalog
        owns the secret reference and the shape of the configuration.
        """
        with self._session_factory() as session:
            datasource = TenantScopedRepository(session, ctx.tenant_id).get(Datasource, datasource_id)
            if datasource is None:
                raise NotFoundError("Datasource not found")
            self._validate_datasource(datasource.kind, datasource.config, datasource.secret_ref)
            return True

    @staticmethod
    def _validate_datasource(kind: str, config: dict[str, Any], secret_ref: str | None) -> None:
        if not kind:
            raise InvalidArgumentError("datasource kind is required")
        if kind in {"mysql", "postgres", "postgresql"}:
            missing = [key for key in ("host", "database") if not config.get(key)]
        elif kind in {"http", "rest"}:
            missing = [key for key in ("base_url",) if not config.get(key)]
        else:
            missing = []
        if missing:
            raise InvalidArgumentError("datasource config is incomplete", missing=missing)
        if secret_ref is not None and not secret_ref.startswith("secret://"):
            raise InvalidArgumentError("secret_ref must use the secret:// scheme")

    def create_dataset(
        self,
        ctx: TenantContext,
        *,
        project_id: str,
        name: str,
        description: str = "",
        tags: Sequence[str] = (),
    ) -> DatasetView:
        if not name.strip():
            raise InvalidArgumentError("dataset name is required")
        with self._session_factory() as session:
            project = TenantScopedRepository(session, ctx.tenant_id).get(Project, project_id)
            if project is None or project.deleted_at is not None:
                raise NotFoundError("Project not found")
            exists = session.scalar(
                select(Dataset).where(
                    Dataset.tenant_id == ctx.tenant_id,
                    Dataset.project_id == project_id,
                    Dataset.name == name.strip(),
                )
            )
            if exists is not None:
                raise InvalidArgumentError("dataset already exists", name=name)
            dataset = Dataset(
                id=new_ulid(),
                tenant_id=ctx.tenant_id,
                project_id=project_id,
                name=name.strip(),
                description=description,
                tags=list(tags),
                created_by=ctx.subject_id,
            )
            session.add(dataset)
            session.commit()
            return _dataset_view(dataset)

    def publish_version(
        self,
        ctx: TenantContext,
        dataset_id: str,
        samples: Sequence[dict[str, Any]],
        *,
        schema_fields: Sequence[SchemaField] = (),
    ) -> DatasetVersionRef:
        normalized = _normalize_samples(samples)
        _validate_schema(normalized, schema_fields)
        digest = content_hash(normalized)
        with self._session_factory() as session:
            dataset = TenantScopedRepository(session, ctx.tenant_id).get(Dataset, dataset_id)
            if dataset is None or dataset.deleted_at is not None:
                raise NotFoundError("Dataset not found")

            existing = session.scalar(
                select(DatasetVersion).where(
                    DatasetVersion.tenant_id == ctx.tenant_id,
                    DatasetVersion.dataset_id == dataset_id,
                    DatasetVersion.content_hash == digest,
                )
            )
            if existing is not None:
                return _version_ref(existing)

            version_number = (
                session.scalar(
                    select(func.max(DatasetVersion.version)).where(
                        DatasetVersion.tenant_id == ctx.tenant_id,
                        DatasetVersion.dataset_id == dataset_id,
                    )
                )
                or 0
            ) + 1
            version_id = new_ulid()
            version = DatasetVersion(
                id=version_id,
                tenant_id=ctx.tenant_id,
                dataset_id=dataset_id,
                version=version_number,
                content_hash=digest,
                row_count=len(normalized),
                schema_fields=[field.__dict__ for field in schema_fields],
                created_by=ctx.subject_id,
            )
            session.add(version)

            rows = [
                {
                    "id": new_ulid(),
                    "tenant_id": ctx.tenant_id,
                    "dataset_version_id": version_id,
                    "dataset_id": dataset_id,
                    "version": version_number,
                    "sample_key": sample["sample_key"],
                    "payload": sample["payload"],
                    "artifact_id": sample["artifact_id"],
                    "created_at": utcnow_naive(),
                }
                for sample in normalized
            ]
            for start in range(0, len(rows), 1000):
                session.execute(insert(Sample), rows[start : start + 1000])

            dataset.latest_version = version_number
            dataset.sample_count = len(rows)
            dataset.updated_at = utcnow_naive()
            try:
                session.commit()
            except IntegrityError as exc:
                raise InvalidArgumentError("version already exists", dataset_id=dataset_id) from exc
            return _version_ref(version)

    def get_version(self, ctx: TenantContext, ref: DatasetVersionRef) -> DatasetVersionView:
        with self._session_factory() as session:
            version = session.scalar(
                select(DatasetVersion).where(
                    DatasetVersion.tenant_id == ctx.tenant_id,
                    DatasetVersion.dataset_id == ref.dataset_id,
                    DatasetVersion.version == ref.version,
                )
            )
            if version is None:
                raise NotFoundError("Dataset version not found")
            fields = tuple(SchemaField(**field) for field in version.schema_fields)
            return DatasetVersionView(ref=_version_ref(version), row_count=version.row_count, fields=fields)

    def get_schema(
        self,
        ctx: TenantContext,
        dataset_id: str,
        version: int | None = None,
    ) -> DatasetVersionView:
        if version is None:
            with self._session_factory() as session:
                latest = session.scalar(
                    select(func.max(DatasetVersion.version)).where(
                        DatasetVersion.tenant_id == ctx.tenant_id,
                        DatasetVersion.dataset_id == dataset_id,
                    )
                )
            if latest is None:
                raise NotFoundError("Dataset version not found")
            version = latest
        return self.get_version(ctx, DatasetVersionRef(ctx.tenant_id, dataset_id, version, ""))

    def page_samples(
        self,
        ctx: TenantContext,
        ref: DatasetVersionRef,
        cursor: str | None = None,
        limit: int = 20,
    ) -> Page[SampleView]:
        page_size = clamp_limit(limit, default=20, maximum=100)
        statement = select(Sample).where(
            Sample.tenant_id == ctx.tenant_id,
            Sample.dataset_id == ref.dataset_id,
            Sample.version == ref.version,
        )
        if cursor:
            payload = _decode_cursor(cursor)
            statement = statement.where(Sample.sample_key > payload["k"])
        statement = statement.order_by(Sample.sample_key).limit(page_size + 1)
        with self._session_factory() as session:
            rows = list(session.scalars(statement))
        items = rows[:page_size]
        next_cursor = _encode_cursor({"k": items[-1].sample_key}) if len(rows) > page_size and items else None
        return Page(
            items=[
                SampleView(
                    id=row.id,
                    sample_key=row.sample_key,
                    payload=row.payload,
                    artifact_id=row.artifact_id,
                )
                for row in items
            ],
            next_cursor=next_cursor,
            truncated=len(rows) > page_size,
        )

    def search_datasets(
        self,
        ctx: TenantContext,
        query: DatasetQuery | None = None,
        cursor: str | None = None,
        limit: int = 20,
    ) -> Page[DatasetView]:
        query = query or DatasetQuery()
        page_size = clamp_limit(limit, default=20, maximum=100)
        statement = select(Dataset).where(
            Dataset.tenant_id == ctx.tenant_id,
            Dataset.deleted_at.is_(None),
        )
        if query.query:
            statement = statement.where(Dataset.name.like(f"%{query.query}%"))
        if query.project_id:
            statement = statement.where(Dataset.project_id == query.project_id)
        if cursor:
            payload = _decode_cursor(cursor)
            stamp = datetime.fromisoformat(payload["t"])
            statement = statement.where(
                or_(
                    Dataset.updated_at < stamp,
                    and_(Dataset.updated_at == stamp, Dataset.id < payload["id"]),
                )
            )
        statement = statement.order_by(Dataset.updated_at.desc(), Dataset.id.desc()).limit(page_size + 1)
        with self._session_factory() as session:
            rows = list(session.scalars(statement))
        if query.tags:
            wanted = set(query.tags)
            rows = [row for row in rows if wanted.issubset(set(row.tags or ()))]
        items = rows[:page_size]
        next_cursor = (
            _encode_cursor({"t": items[-1].updated_at.isoformat(), "id": items[-1].id})
            if len(rows) > page_size and items
            else None
        )
        return Page(
            items=[_dataset_view(row) for row in items],
            next_cursor=next_cursor,
            truncated=len(rows) > page_size,
        )

    # Lineage ---------------------------------------------------------------

    def add_lineage(
        self,
        ctx: TenantContext,
        *,
        upstream_type: str,
        upstream_id: str,
        downstream_type: str,
        downstream_id: str,
    ) -> None:
        with self._session_factory() as session:
            session.add(
                LineageEdge(
                    id=new_ulid(),
                    tenant_id=ctx.tenant_id,
                    upstream_type=upstream_type,
                    upstream_id=upstream_id,
                    downstream_type=downstream_type,
                    downstream_id=downstream_id,
                )
            )
            session.commit()

    def trace_lineage(self, ctx: TenantContext, *, node_type: str, node_id: str) -> list[LineageEdge]:
        with self._session_factory() as session:
            statement = select(LineageEdge).where(
                LineageEdge.tenant_id == ctx.tenant_id,
                or_(
                    and_(LineageEdge.upstream_type == node_type, LineageEdge.upstream_id == node_id),
                    and_(LineageEdge.downstream_type == node_type, LineageEdge.downstream_id == node_id),
                ),
            )
            return list(session.scalars(statement))


def _reject_plaintext_secrets(config: dict[str, Any]) -> None:
    sensitive = {"password", "passwd", "secret", "token", "api_key", "raw_key", "private_key"}
    for key in config:
        if str(key).lower() in sensitive:
            raise InvalidArgumentError("datasource config must use secret_ref, not plaintext secrets", key=str(key))


def _project_view(row: Project) -> ProjectView:
    return ProjectView(id=row.id, tenant_id=row.tenant_id, name=row.name, description=row.description)


def _dataset_view(row: Dataset) -> DatasetView:
    return DatasetView(
        id=row.id,
        tenant_id=row.tenant_id,
        project_id=row.project_id,
        name=row.name,
        latest_version=row.latest_version,
        sample_count=row.sample_count,
        tags=tuple(row.tags or ()),
    )


def _version_ref(row: DatasetVersion) -> DatasetVersionRef:
    return DatasetVersionRef(
        tenant_id=row.tenant_id,
        dataset_id=row.dataset_id,
        version=row.version,
        content_hash=row.content_hash,
    )
