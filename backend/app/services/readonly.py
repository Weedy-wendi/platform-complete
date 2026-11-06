"""SQL-backed read-only services for the deployed MCP server.

The default MCP wiring is intentionally in-memory so the adapter can run
without the platform. Production deployments set::

    PINGCE_MCP_SERVICES_FACTORY=app.services.readonly:build_readonly_services

and this module builds the real registry from the read-only database account.
Every repository opens its own short-lived session; no writes are performed.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any, cast

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.core.db import (
    create_readonly_engine_from_dsn,
    make_session_factory,
)
from app.modules.catalog.models import (
    Dataset as DatasetRow,
)
from app.modules.catalog.models import (
    DatasetVersion as DatasetVersionRow,
)
from app.modules.catalog.models import (
    Project as ProjectRow,
)
from app.modules.catalog.models import (
    Sample as SampleRow,
)
from app.modules.evaluation.models import (
    Evaluator as EvaluatorRow,
)
from app.modules.evaluation.models import (
    Metric as MetricRow,
)
from app.modules.evaluation.models import (
    Run as RunRow,
)
from app.modules.evaluation.models import (
    RunItem as RunItemRow,
)
from app.modules.evaluation.models import (
    Score as ScoreRow,
)
from app.modules.gate.models import GateResultRecord
from app.services import ServiceRegistry
from app.services.badcases import BadcaseService
from app.services.datasets import DatasetService
from app.services.evaluation import EvaluationService
from app.services.models import (
    Badcase,
    BadcaseHit,
    BadcaseSearchResult,
    Dataset,
    DatasetVersion,
    Evaluator,
    EvaluatorKind,
    GateResult,
    GateRuleResult,
    MetricDefinition,
    MetricDirection,
    MetricValue,
    Project,
    Run,
    RunError,
    RunItem,
    RunItemStatus,
    RunStatus,
    RunTarget,
    Sample,
    SchemaField,
)
from app.services.projects import ProjectService

SessionFactory = sessionmaker[Session]

_RUN_STATUSES = {
    "queued",
    "dispatching",
    "running",
    "succeeded",
    "succeeded_with_errors",
    "failed",
    "cancelled",
    "timed_out",
}
_ITEM_STATUSES = {"succeeded", "failed", "skipped", "error"}
_ITEM_STATUS_MAP = {"pending": "skipped"}
_EVALUATOR_KINDS = {"rule", "judge", "human"}


def _session(factory: SessionFactory) -> Session:
    return factory()


def _direction(value: str | None) -> MetricDirection:
    return "lower_is_better" if value == "lower_is_better" else "higher_is_better"


class SqlProjectRepository:
    def __init__(self, factory: SessionFactory) -> None:
        self._factory = factory

    def list_for_tenant(self, tenant_id: str) -> Sequence[Project]:
        with _session(self._factory) as session:
            rows = session.scalars(
                select(ProjectRow)
                .where(ProjectRow.tenant_id == tenant_id, ProjectRow.deleted_at.is_(None))
                .order_by(ProjectRow.updated_at.desc())
            )
            return [
                Project(
                    id=row.id,
                    tenant_id=row.tenant_id,
                    name=row.name,
                    description=row.description or None,
                    updated_at=row.updated_at,
                )
                for row in rows
            ]


class SqlDatasetRepository:
    def __init__(self, factory: SessionFactory) -> None:
        self._factory = factory

    def list_for_tenant(self, tenant_id: str) -> Sequence[Dataset]:
        with _session(self._factory) as session:
            rows = session.scalars(
                select(DatasetRow)
                .where(DatasetRow.tenant_id == tenant_id, DatasetRow.deleted_at.is_(None))
                .order_by(DatasetRow.updated_at.desc())
            )
            return [
                Dataset(
                    id=row.id,
                    tenant_id=row.tenant_id,
                    project_id=row.project_id,
                    name=row.name,
                    latest_version=row.latest_version,
                    sample_count=row.sample_count,
                    tags=tuple(row.tags or ()),
                    updated_at=row.updated_at,
                )
                for row in rows
            ]

    def get_version(self, tenant_id: str, dataset_id: str, version: int | None) -> DatasetVersion | None:
        with _session(self._factory) as session:
            statement = select(DatasetVersionRow).where(
                DatasetVersionRow.tenant_id == tenant_id,
                DatasetVersionRow.dataset_id == dataset_id,
            )
            if version is None:
                statement = statement.order_by(DatasetVersionRow.version.desc()).limit(1)
            else:
                statement = statement.where(DatasetVersionRow.version == version)
            row = session.scalars(statement).first()
            if row is None:
                return None
            fields = tuple(
                SchemaField(
                    name=str(item.get("name", "")),
                    type=str(item.get("type", "unknown")),
                    nullable=bool(item.get("nullable", True)),
                    description=item.get("description"),
                )
                for item in (row.schema_fields or ())
                if isinstance(item, dict)
            )
            return DatasetVersion(
                dataset_id=row.dataset_id,
                tenant_id=row.tenant_id,
                version=row.version,
                content_hash=row.content_hash,
                row_count=row.row_count,
                fields=fields,
                schema_json={"fields": list(row.schema_fields or ())},
            )

    def list_samples(self, tenant_id: str, dataset_id: str, version: int) -> Sequence[Sample]:
        with _session(self._factory) as session:
            rows = session.scalars(
                select(SampleRow)
                .where(
                    SampleRow.tenant_id == tenant_id,
                    SampleRow.dataset_id == dataset_id,
                    SampleRow.version == version,
                )
                .order_by(SampleRow.sample_key)
            )
            return [
                Sample(
                    id=row.id,
                    tenant_id=row.tenant_id,
                    dataset_id=row.dataset_id,
                    version=row.version,
                    payload=dict(row.payload or {}),
                    tags=tuple((row.payload or {}).get("tags") or ()),
                )
                for row in rows
            ]


class SqlEvaluatorRepository:
    def __init__(self, factory: SessionFactory) -> None:
        self._factory = factory

    def list_for_tenant(self, tenant_id: str, project_id: str | None = None) -> Sequence[Evaluator]:
        del project_id  # evaluators are tenant-global in the current schema
        with _session(self._factory) as session:
            rows = session.scalars(select(EvaluatorRow).where(EvaluatorRow.tenant_id == tenant_id))
            metrics = session.scalars(select(MetricRow).where(MetricRow.tenant_id == tenant_id)).all()
            by_evaluator: dict[str, list[MetricRow]] = {}
            for metric in metrics:
                if metric.evaluator_id:
                    by_evaluator.setdefault(metric.evaluator_id, []).append(metric)
            result: list[Evaluator] = []
            for row in rows:
                kind = row.kind if row.kind in _EVALUATOR_KINDS else "rule"
                result.append(
                    Evaluator(
                        id=row.id,
                        tenant_id=row.tenant_id,
                        name=row.name,
                        version=str(row.latest_version),
                        kind=cast(EvaluatorKind, kind),
                        project_id=None,
                        description=row.description or None,
                        metrics=tuple(
                            MetricDefinition(name=item.name, direction=_direction(item.direction))
                            for item in by_evaluator.get(row.id, ())
                        ),
                        published=True,
                    )
                )
            return result


class SqlRunRepository:
    def __init__(self, factory: SessionFactory) -> None:
        self._factory = factory

    def get(self, tenant_id: str, run_id: str) -> Run | None:
        with _session(self._factory) as session:
            row = session.get(RunRow, run_id)
            if row is None or row.tenant_id != tenant_id:
                return None
            metrics = _run_metrics(session, tenant_id, run_id)
            return Run(
                id=row.id,
                tenant_id=row.tenant_id,
                status=cast(RunStatus, row.status if row.status in _RUN_STATUSES else "failed"),
                progress=float(row.progress or 0),
                manifest_hash=row.manifest_hash,
                suite_id=row.suite_id,
                suite_version=str(row.suite_version) if row.suite_version is not None else None,
                dataset_id=row.dataset_id or None,
                dataset_version=row.dataset_version or None,
                target=_run_target(row.manifest),
                started_at=row.started_at,
                finished_at=row.finished_at,
                metrics=metrics,
                cost_usd=float(row.cost_usd or 0.0),
                item_total=row.total_items,
                item_succeeded=row.succeeded_items,
                item_failed=row.failed_items,
                item_skipped=row.skipped_items,
                error=RunError(code="RUN_FAILED", message=row.error) if row.error else None,
            )

    def list_items(self, tenant_id: str, run_id: str) -> Sequence[RunItem]:
        with _session(self._factory) as session:
            rows = session.scalars(
                select(RunItemRow)
                .where(RunItemRow.tenant_id == tenant_id, RunItemRow.run_id == run_id)
                .order_by(RunItemRow.sample_index)
            )
            scores = session.scalars(
                select(ScoreRow).where(ScoreRow.tenant_id == tenant_id, ScoreRow.run_id == run_id)
            ).all()
            by_item: dict[str, list[ScoreRow]] = {}
            directions = {
                item.name: _direction(item.direction)
                for item in session.scalars(select(MetricRow).where(MetricRow.tenant_id == tenant_id))
            }
            for score in scores:
                by_item.setdefault(score.run_item_id, []).append(score)
            result: list[RunItem] = []
            for row in rows:
                item_scores = by_item.get(row.id, [])
                metrics = tuple(
                    MetricValue(
                        name=score.metric_name,
                        value=float(score.value),
                        direction=directions.get(score.metric_name, "higher_is_better"),
                    )
                    for score in item_scores
                )
                result.append(
                    RunItem(
                        id=row.id,
                        tenant_id=row.tenant_id,
                        run_id=row.run_id,
                        sample_id=row.sample_key,
                        status=cast(
                            RunItemStatus,
                            row.status if row.status in _ITEM_STATUSES else _ITEM_STATUS_MAP.get(row.status, "failed"),
                        ),
                        score=(sum(score.value for score in item_scores) / len(item_scores)) if item_scores else None,
                        latency_ms=row.latency_ms,
                        tokens=None,
                        error=RunError(code="RUN_ITEM_FAILED", message=row.error) if row.error else None,
                        evidence_ref=row.raw_ref,
                        input=json.dumps(row.payload or {}, ensure_ascii=False),
                        output=row.output,
                        metrics=metrics,
                    )
                )
            return result


class SqlBadcaseSearch:
    """Keyword fallback over failed run items (degraded, no vector store)."""

    def __init__(self, factory: SessionFactory) -> None:
        self._factory = factory

    def search_badcases(
        self,
        *,
        tenant_id: str,
        query: str | None,
        dataset_id: str | None,
        tags: tuple[str, ...],
        limit: int,
    ) -> BadcaseSearchResult:
        needle = query.strip().lower() if query else None
        wanted_tags = set(tags)
        with _session(self._factory) as session:
            statement = (
                select(RunItemRow, RunRow.dataset_id)
                .join(RunRow, RunRow.id == RunItemRow.run_id)
                .where(
                    RunItemRow.tenant_id == tenant_id,
                    RunItemRow.status.in_(("failed", "error")),
                )
                .order_by(RunItemRow.created_at.desc())
                .limit(max(limit * 5, limit))
            )
            if dataset_id is not None:
                statement = statement.where(RunRow.dataset_id == dataset_id)
            rows = session.execute(statement).all()
            hits: list[BadcaseHit] = []
            for item, row_dataset_id in rows:
                payload = item.payload or {}
                item_tags = tuple(payload.get("tags") or ())
                if wanted_tags and not wanted_tags.issubset(set(item_tags)):
                    continue
                haystack = " ".join(
                    [
                        item.sample_key,
                        item.output or "",
                        item.error or "",
                        json.dumps(payload, ensure_ascii=False),
                    ]
                ).lower()
                if needle and needle not in haystack:
                    continue
                hits.append(
                    BadcaseHit(
                        badcase=Badcase(
                            id=item.id,
                            tenant_id=item.tenant_id,
                            title=item.sample_key,
                            dataset_id=row_dataset_id,
                            sample_id=item.sample_key,
                            tags=item_tags,
                            created_at=item.created_at,
                            evidence_ref=item.raw_ref,
                        ),
                        similarity=None,
                    )
                )
                if len(hits) >= limit:
                    break
            return BadcaseSearchResult(hits=hits, degraded=True)


class SqlGateReader:
    def __init__(self, factory: SessionFactory) -> None:
        self._factory = factory

    def read_gate(self, *, tenant_id: str, suite_id: str, run_id: str) -> GateResult | None:
        with _session(self._factory) as session:
            row = session.scalars(
                select(GateResultRecord)
                .where(
                    GateResultRecord.tenant_id == tenant_id,
                    GateResultRecord.suite_id == suite_id,
                    GateResultRecord.run_id == run_id,
                )
                .order_by(GateResultRecord.evaluated_at.desc())
                .limit(1)
            ).first()
            if row is None:
                return None
            rules = tuple(
                GateRuleResult(
                    name=str(item.get("name", "")),
                    expected=str(item.get("expected", "")),
                    actual=str(item.get("actual", "")),
                    passed=bool(item.get("passed", False)),
                    evidence_ref=item.get("evidence_ref"),
                )
                for item in (row.rules or ())
                if isinstance(item, dict)
            )
            return GateResult(
                tenant_id=row.tenant_id,
                suite_id=row.suite_id,
                run_id=row.run_id,
                passed=row.passed,
                rules=rules,
                manifest_hash=row.manifest_hash,
                evaluated_at=row.evaluated_at,
            )


def _run_metrics(session: Session, tenant_id: str, run_id: str) -> tuple[MetricValue, ...]:
    rows = session.execute(
        select(ScoreRow.metric_name, func.avg(ScoreRow.value))
        .where(ScoreRow.tenant_id == tenant_id, ScoreRow.run_id == run_id)
        .group_by(ScoreRow.metric_name)
    ).all()
    directions = {
        item.name: _direction(item.direction)
        for item in session.scalars(select(MetricRow).where(MetricRow.tenant_id == tenant_id))
    }
    return tuple(
        MetricValue(name=name, value=float(value), direction=directions.get(name, "higher_is_better"))
        for name, value in rows
    )


def _run_target(manifest: dict[str, Any] | None) -> RunTarget | None:
    if not isinstance(manifest, dict):
        return None
    raw = manifest.get("target_config") or manifest.get("target")
    if not isinstance(raw, dict):
        return None
    provider = raw.get("provider")
    model = raw.get("model")
    if not provider or not model:
        return None
    return RunTarget(provider=str(provider), model=str(model))


def build_readonly_services(settings: Settings) -> ServiceRegistry:
    """Build a ``ServiceRegistry`` backed by the read-only MySQL account."""

    dsn = settings.mcp_db_dsn or settings.read_database_url
    if not dsn:
        raise ValueError("PINGCE_MCP_DB_DSN or PINGCE_DATABASE_URL is required to build read-only services")
    engine = create_readonly_engine_from_dsn(dsn)
    factory = make_session_factory(engine)
    return ServiceRegistry(
        projects=ProjectService(SqlProjectRepository(factory)),
        datasets=DatasetService(SqlDatasetRepository(factory)),
        evaluation=EvaluationService(SqlEvaluatorRepository(factory), SqlRunRepository(factory)),
        badcases=BadcaseService(SqlBadcaseSearch(factory)),
        gate=SqlGateReader(factory),
    )


__all__ = [
    "SqlBadcaseSearch",
    "SqlDatasetRepository",
    "SqlEvaluatorRepository",
    "SqlGateReader",
    "SqlProjectRepository",
    "SqlRunRepository",
    "build_readonly_services",
]
