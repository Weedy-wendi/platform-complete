"""Ingestion use cases: connectors, resumable sync, schema drift, quality."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.core.clock import utcnow_naive
from app.core.context import TenantContext
from app.core.errors import InvalidArgumentError, NotFoundError
from app.core.ids import new_ulid
from app.core.repository import TenantScopedRepository
from app.modules.ingestion.connectors import ConnectorRegistry, default_registry
from app.modules.ingestion.models import (
    ConnectorRecord,
    IngestionDeadLetter,
    IngestionJob,
    QualityResult,
    QualityRule,
    SyncCursor,
)
from app.modules.ingestion.public import (
    CancellationSignal,
    ConnectorCursor,
    ConnectorDescriptor,
    ConnectorField,
    QualityReport,
    QualityResultView,
    QualityRuleSpec,
    SampleWriter,
    SyncResult,
)
from app.modules.ingestion.quality import evaluate_rules
from app.modules.ingestion.schema import detect_drift, infer_schema, schema_to_records
from app.modules.ingestion.transform import apply_transform, dedupe_rows, validate_transform

_SUPPORTED_SEVERITIES = {"error", "warning", "info"}


def _reject_plaintext_secrets(config: dict[str, Any]) -> None:
    sensitive = {"password", "passwd", "secret", "token", "api_key", "raw_key", "private_key", "authorization"}
    for key in config:
        lowered = str(key).lower()
        if lowered in sensitive or lowered.endswith("_token") or lowered.endswith("_secret"):
            raise InvalidArgumentError(
                "connector config must use secret_ref, not plaintext secrets",
                key=str(key),
            )


def _descriptor(record: ConnectorRecord) -> ConnectorDescriptor:
    return ConnectorDescriptor(
        id=record.id,
        tenant_id=record.tenant_id,
        name=record.name,
        kind=record.kind,
        config=record.config or {},
        transform=record.transform,
        dedupe_key=record.dedupe_key,
        secret_ref=record.secret_ref,
        status=record.status,
    )


def _result(
    job: IngestionJob,
    cursor: ConnectorCursor,
) -> SyncResult:
    return SyncResult(
        job_id=job.id,
        rows_read=job.rows_read,
        rows_written=job.rows_written,
        rows_skipped=job.rows_skipped,
        next_cursor=cursor,
    )


class IngestionService:
    """Concrete ingestion orchestration.

    The catalog is reached exclusively through the injected :class:`SampleWriter`
    callback; this module never imports catalog models or services.
    """

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        registry: ConnectorRegistry | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._registry = registry or default_registry()

    # Connectors -----------------------------------------------------------

    def create_connector(
        self,
        ctx: TenantContext,
        *,
        name: str,
        kind: str,
        config: dict[str, Any],
        secret_ref: str | None = None,
        transform: dict[str, Any] | None = None,
        dedupe_key: str | None = None,
    ) -> ConnectorDescriptor:
        if not name.strip():
            raise InvalidArgumentError("connector name is required")
        if not kind.strip():
            raise InvalidArgumentError("connector kind is required")
        _reject_plaintext_secrets(config)
        if secret_ref is not None and not secret_ref.startswith("secret://"):
            raise InvalidArgumentError("secret_ref must use the secret:// scheme")
        validate_transform(transform)
        if dedupe_key is not None and not dedupe_key.strip():
            raise InvalidArgumentError("dedupe_key must not be empty")
        # Validate the descriptor shape early, but do not perform network IO.
        self._registry.create(kind, config)
        with self._session_factory() as session:
            duplicate = session.scalar(
                select(ConnectorRecord).where(
                    ConnectorRecord.tenant_id == ctx.tenant_id,
                    ConnectorRecord.name == name.strip(),
                )
            )
            if duplicate is not None:
                raise InvalidArgumentError("connector already exists", name=name)
            record = ConnectorRecord(
                id=new_ulid(),
                tenant_id=ctx.tenant_id,
                name=name.strip(),
                kind=kind,
                config=config,
                transform=transform,
                dedupe_key=dedupe_key.strip() if dedupe_key else None,
                secret_ref=secret_ref,
                created_by=ctx.subject_id,
            )
            session.add(record)
            session.commit()
            return _descriptor(record)

    def get_connector(self, ctx: TenantContext, connector_id: str) -> ConnectorDescriptor:
        with self._session_factory() as session:
            record = TenantScopedRepository(session, ctx.tenant_id).get(ConnectorRecord, connector_id)
            if record is None:
                raise NotFoundError("Connector not found")
            return _descriptor(record)

    # Quality rules --------------------------------------------------------

    def add_quality_rule(
        self,
        ctx: TenantContext,
        *,
        name: str,
        rule_type: str,
        config: dict[str, Any],
        severity: str = "error",
    ) -> QualityRuleSpec:
        if not name.strip():
            raise InvalidArgumentError("quality rule name is required")
        if severity not in _SUPPORTED_SEVERITIES:
            raise InvalidArgumentError("unsupported quality severity", severity=severity)
        with self._session_factory() as session:
            record = QualityRule(
                id=new_ulid(),
                tenant_id=ctx.tenant_id,
                name=name.strip(),
                rule_type=rule_type,
                config=config,
                severity=severity,
                created_by=ctx.subject_id,
            )
            session.add(record)
            session.commit()
            return QualityRuleSpec(record.id, record.rule_type, record.config, record.severity)

    # Sync -----------------------------------------------------------------

    def sync(
        self,
        ctx: TenantContext,
        *,
        connector_id: str,
        dataset_id: str,
        writer: SampleWriter,
        idempotency_key: str,
        rules: Sequence[QualityRuleSpec] = (),
        batch_size: int = 100,
        cancel: CancellationSignal | None = None,
        transform: dict[str, Any] | None = None,
        dedupe_key: str | None = None,
    ) -> SyncResult:
        if not idempotency_key.strip():
            raise InvalidArgumentError("idempotency_key is required")
        if not dataset_id.strip():
            raise InvalidArgumentError("dataset_id is required")
        if not 1 <= batch_size <= 10_000:
            raise InvalidArgumentError("batch_size must be between 1 and 10000")
        validate_transform(transform)
        try:
            connector_config, connector_kind, connector_transform, connector_dedupe = self._load_connector(
                ctx, connector_id
            )
            connector = self._registry.create(connector_kind, connector_config)
        except InvalidArgumentError:
            raise

        effective_transform = transform if transform is not None else connector_transform
        effective_dedupe = dedupe_key if dedupe_key is not None else connector_dedupe
        job, initial_cursor, previous_schema, rule_specs = self._begin_job(
            ctx,
            connector_id=connector_id,
            dataset_id=dataset_id,
            idempotency_key=idempotency_key,
            rules=rules,
            transform=effective_transform,
            dedupe_key=effective_dedupe,
        )
        if job.status in {"succeeded", "failed", "cancelled"}:
            return _result(job, initial_cursor)
        effective_transform = job.transform or {}
        effective_dedupe = job.dedupe_key

        rows_read = 0
        rows_written = 0
        rows_skipped = 0
        persisted_cursor = initial_cursor
        drift_alerts: list[dict[str, Any]] = []
        current = initial_cursor
        batch_index = 0
        seen_dedupe: set[str] = set()

        while True:
            if cancel is not None and cancel.is_set():
                self._finish(
                    ctx,
                    job.id,
                    status="cancelled",
                    rows_read=rows_read,
                    rows_written=rows_written,
                    rows_skipped=rows_skipped,
                    cursor=persisted_cursor,
                    drift=drift_alerts,
                    error="cancelled by caller",
                )
                return SyncResult(
                    job_id=job.id,
                    rows_read=rows_read,
                    rows_written=rows_written,
                    rows_skipped=rows_skipped,
                    next_cursor=persisted_cursor,
                )

            try:
                rows, next_cursor = connector.read(current, batch_size)
            except Exception as exc:  # noqa: BLE001 - persisted as a failed job
                self._finish(
                    ctx,
                    job.id,
                    status="failed",
                    rows_read=rows_read,
                    rows_written=rows_written,
                    rows_skipped=rows_skipped,
                    cursor=persisted_cursor,
                    drift=drift_alerts,
                    error=str(exc),
                )
                return SyncResult(
                    job_id=job.id,
                    rows_read=rows_read,
                    rows_written=rows_written,
                    rows_skipped=rows_skipped,
                    next_cursor=persisted_cursor,
                )

            if not rows:
                self._finish(
                    ctx,
                    job.id,
                    status="succeeded",
                    rows_read=rows_read,
                    rows_written=rows_written,
                    rows_skipped=rows_skipped,
                    cursor=persisted_cursor,
                    drift=drift_alerts,
                )
                return SyncResult(
                    job_id=job.id,
                    rows_read=rows_read,
                    rows_written=rows_written,
                    rows_skipped=rows_skipped,
                    next_cursor=persisted_cursor,
                )

            rows_read += len(rows)
            try:
                transformed = apply_transform(rows, effective_transform)
                ready_rows, duplicates = dedupe_rows(transformed, effective_dedupe, seen_dedupe)
            except Exception as exc:  # noqa: BLE001 - persisted as a failed job
                self._finish(
                    ctx,
                    job.id,
                    status="failed",
                    rows_read=rows_read,
                    rows_written=rows_written,
                    rows_skipped=rows_skipped,
                    cursor=persisted_cursor,
                    drift=drift_alerts,
                    error=f"transform failed: {exc}",
                )
                return SyncResult(
                    job_id=job.id,
                    rows_read=rows_read,
                    rows_written=rows_written,
                    rows_skipped=rows_skipped,
                    next_cursor=persisted_cursor,
                )
            rows_skipped += duplicates
            inferred = infer_schema(ready_rows)
            drift = detect_drift(previous_schema, inferred)
            if drift.has_drift:
                drift_alerts.extend(drift.alerts())

            report = evaluate_rules(ready_rows, rule_specs)
            if not report.passed:
                self._persist_quality(ctx, job.id, dataset_id, report)
                failed_rules = ", ".join(result.rule_id for result in report.failed)
                self._finish(
                    ctx,
                    job.id,
                    status="failed",
                    rows_read=rows_read,
                    rows_written=rows_written,
                    rows_skipped=rows_skipped,
                    cursor=persisted_cursor,
                    drift=drift_alerts,
                    error=f"quality check failed: {failed_rules}",
                )
                return SyncResult(
                    job_id=job.id,
                    rows_read=rows_read,
                    rows_written=rows_written,
                    rows_skipped=rows_skipped,
                    next_cursor=persisted_cursor,
                )

            written = 0
            if ready_rows:
                batch_key = f"{idempotency_key}:{batch_index}"
                try:
                    written = writer.write_batch(
                        tenant_id=ctx.tenant_id,
                        dataset_id=dataset_id,
                        idempotency_key=batch_key,
                        rows=ready_rows,
                    )
                except Exception as exc:  # noqa: BLE001 - rollback must be attempted
                    try:
                        writer.rollback_batch(
                            tenant_id=ctx.tenant_id,
                            dataset_id=dataset_id,
                            idempotency_key=batch_key,
                        )
                    except Exception:  # noqa: BLE001 - the original failure wins
                        pass
                    self._finish(
                        ctx,
                        job.id,
                        status="failed",
                        rows_read=rows_read,
                        rows_written=rows_written,
                        rows_skipped=rows_skipped,
                        cursor=persisted_cursor,
                        drift=drift_alerts,
                        error=f"sample write failed: {exc}",
                    )
                    return SyncResult(
                        job_id=job.id,
                        rows_read=rows_read,
                        rows_written=rows_written,
                        rows_skipped=rows_skipped,
                        next_cursor=persisted_cursor,
                    )

                written = max(0, min(written, len(ready_rows)))
            rows_written += written
            rows_skipped += len(ready_rows) - written
            persisted_cursor = ConnectorCursor(value=next_cursor.value, updated_at=next_cursor.updated_at)
            previous_schema = inferred
            self._commit_batch(
                ctx,
                connector_id=connector_id,
                dataset_id=dataset_id,
                job_id=job.id,
                cursor=next_cursor,
                schema_fields=schema_to_records(inferred),
                report=report,
                rows_read=rows_read,
                rows_written=rows_written,
                rows_skipped=rows_skipped,
                drift=drift_alerts,
            )
            batch_index += 1

            if len(rows) < batch_size or next_cursor.value is None:
                self._finish(
                    ctx,
                    job.id,
                    status="succeeded",
                    rows_read=rows_read,
                    rows_written=rows_written,
                    rows_skipped=rows_skipped,
                    cursor=persisted_cursor,
                    drift=drift_alerts,
                )
                return SyncResult(
                    job_id=job.id,
                    rows_read=rows_read,
                    rows_written=rows_written,
                    rows_skipped=rows_skipped,
                    next_cursor=persisted_cursor,
                )
            current = next_cursor

    # Queries --------------------------------------------------------------

    def get_job(self, ctx: TenantContext, job_id: str) -> dict[str, Any]:
        with self._session_factory() as session:
            job = TenantScopedRepository(session, ctx.tenant_id).get(IngestionJob, job_id)
            if job is None:
                raise NotFoundError("Ingestion job not found")
            return {
                "id": job.id,
                "status": job.status,
                "rows_read": job.rows_read,
                "rows_written": job.rows_written,
                "rows_skipped": job.rows_skipped,
                "cursor_value": job.cursor_value,
                "schema_drift": job.schema_drift or [],
                "error": job.error,
            }

    def quality_results(self, ctx: TenantContext, job_id: str) -> list[QualityResultView]:
        with self._session_factory() as session:
            job = TenantScopedRepository(session, ctx.tenant_id).get(IngestionJob, job_id)
            if job is None:
                raise NotFoundError("Ingestion job not found")
            rows = list(
                session.scalars(
                    select(QualityResult)
                    .where(
                        QualityResult.tenant_id == ctx.tenant_id,
                        QualityResult.job_id == job_id,
                    )
                    .order_by(QualityResult.created_at, QualityResult.id)
                )
            )
        return [
            QualityResultView(
                id=row.id,
                job_id=row.job_id,
                rule_id=row.rule_id,
                dataset_id=row.dataset_id,
                passed=row.passed,
                checked_rows=row.checked_rows,
                failed_rows=row.failed_rows,
                details=row.details or {},
                created_at=row.created_at,
            )
            for row in rows
        ]

    def dead_letters(self, ctx: TenantContext) -> list[dict[str, Any]]:
        with self._session_factory() as session:
            rows = list(
                session.scalars(
                    select(IngestionDeadLetter)
                    .where(IngestionDeadLetter.tenant_id == ctx.tenant_id)
                    .order_by(IngestionDeadLetter.created_at, IngestionDeadLetter.id)
                )
            )
        return [_dead_letter_view(row) for row in rows]

    def replay_dead_letter(self, ctx: TenantContext, letter_id: str) -> str:
        """Mark a dead letter replayed and return a fresh, runnable job id."""

        with self._session_factory() as session:
            letter = TenantScopedRepository(session, ctx.tenant_id).get(IngestionDeadLetter, letter_id)
            if letter is None:
                raise NotFoundError("Dead letter not found")
            if letter.replayed:
                raise InvalidArgumentError("dead letter is already replayed")
            payload = dict(letter.payload or {})
            dataset_id = str(payload.get("dataset_id") or "")
            if not dataset_id:
                raise InvalidArgumentError("dead letter is missing dataset_id")
            job_id = new_ulid()
            session.add(
                IngestionJob(
                    id=job_id,
                    tenant_id=ctx.tenant_id,
                    connector_id=letter.connector_id,
                    dataset_id=dataset_id,
                    status="queued",
                    # The job id doubles as the idempotency key so callers can
                    # immediately call sync(..., idempotency_key=job_id).
                    idempotency_key=job_id,
                    transform=payload.get("transform"),
                    dedupe_key=payload.get("dedupe_key"),
                    cursor_value=payload.get("cursor_value"),
                    created_by=ctx.subject_id,
                )
            )
            letter.replayed = True
            session.commit()
            return job_id

    def get_cursor(self, ctx: TenantContext, *, connector_id: str, dataset_id: str) -> ConnectorCursor:
        with self._session_factory() as session:
            cursor = self._find_cursor(session, ctx, connector_id, dataset_id)
            if cursor is None:
                return ConnectorCursor()
            return ConnectorCursor(value=cursor.value, updated_at=cursor.updated_at)

    # Internal -------------------------------------------------------------

    def _load_connector(
        self,
        ctx: TenantContext,
        connector_id: str,
    ) -> tuple[dict[str, Any], str, dict[str, Any] | None, str | None]:
        with self._session_factory() as session:
            record = TenantScopedRepository(session, ctx.tenant_id).get(ConnectorRecord, connector_id)
            if record is None:
                raise NotFoundError("Connector not found")
            return (
                dict(record.config or {}),
                record.kind,
                dict(record.transform) if record.transform else None,
                record.dedupe_key,
            )

    def _begin_job(
        self,
        ctx: TenantContext,
        *,
        connector_id: str,
        dataset_id: str,
        idempotency_key: str,
        rules: Sequence[QualityRuleSpec],
        transform: dict[str, Any] | None = None,
        dedupe_key: str | None = None,
    ) -> tuple[IngestionJob, ConnectorCursor, list[ConnectorField], list[QualityRuleSpec]]:
        with self._session_factory() as session:
            existing = session.scalar(
                select(IngestionJob).where(
                    IngestionJob.tenant_id == ctx.tenant_id,
                    IngestionJob.idempotency_key == idempotency_key,
                )
            )
            cursor = self._find_cursor(session, ctx, connector_id, dataset_id)
            if existing is not None:
                return (
                    existing,
                    ConnectorCursor(
                        value=cursor.value if cursor is not None else existing.cursor_value,
                        updated_at=cursor.updated_at if cursor is not None else None,
                    ),
                    [ConnectorField(**field) for field in (cursor.schema_fields if cursor else [])],
                    [],
                )

            if cursor is None:
                cursor = SyncCursor(
                    id=new_ulid(),
                    tenant_id=ctx.tenant_id,
                    connector_id=connector_id,
                    dataset_id=dataset_id,
                )
                session.add(cursor)
                session.flush()

            job = IngestionJob(
                id=new_ulid(),
                tenant_id=ctx.tenant_id,
                connector_id=connector_id,
                dataset_id=dataset_id,
                status="running",
                idempotency_key=idempotency_key,
                transform=transform,
                dedupe_key=dedupe_key,
                cursor_value=cursor.value,
                started_at=utcnow_naive(),
                created_by=ctx.subject_id,
            )
            session.add(job)
            session.flush()

            if rules:
                specs = list(rules)
            else:
                stored = list(
                    session.scalars(
                        select(QualityRule).where(
                            QualityRule.tenant_id == ctx.tenant_id,
                            QualityRule.enabled.is_(True),
                        )
                    )
                )
                specs = [
                    QualityRuleSpec(
                        rule_id=row.id,
                        rule_type=row.rule_type,
                        config=row.config or {},
                        severity=row.severity,
                    )
                    for row in stored
                ]
            session.commit()
            return (
                job,
                ConnectorCursor(value=cursor.value, updated_at=cursor.updated_at),
                [ConnectorField(**field) for field in (cursor.schema_fields or [])],
                specs,
            )

    @staticmethod
    def _find_cursor(
        session: Session,
        ctx: TenantContext,
        connector_id: str,
        dataset_id: str,
    ) -> SyncCursor | None:
        return session.scalar(
            select(SyncCursor).where(
                SyncCursor.tenant_id == ctx.tenant_id,
                SyncCursor.connector_id == connector_id,
                SyncCursor.dataset_id == dataset_id,
            )
        )

    def _persist_quality(
        self,
        ctx: TenantContext,
        job_id: str,
        dataset_id: str,
        report: QualityReport,
    ) -> None:
        with self._session_factory() as session:
            for result in report.results:
                session.add(
                    QualityResult(
                        id=new_ulid(),
                        tenant_id=ctx.tenant_id,
                        job_id=job_id,
                        rule_id=result.rule_id,
                        dataset_id=dataset_id,
                        passed=result.passed,
                        checked_rows=result.checked_rows,
                        failed_rows=result.failed_rows,
                        details={**result.details, "rule_type": result.rule_type, "severity": result.severity},
                    )
                )
            session.commit()

    def _commit_batch(
        self,
        ctx: TenantContext,
        *,
        connector_id: str,
        dataset_id: str,
        job_id: str,
        cursor: ConnectorCursor,
        schema_fields: list[dict[str, Any]],
        report: QualityReport,
        rows_read: int,
        rows_written: int,
        rows_skipped: int,
        drift: list[dict[str, Any]],
    ) -> None:
        with self._session_factory() as session:
            row = self._find_cursor(session, ctx, connector_id, dataset_id)
            if row is None:
                row = SyncCursor(
                    id=new_ulid(),
                    tenant_id=ctx.tenant_id,
                    connector_id=connector_id,
                    dataset_id=dataset_id,
                )
                session.add(row)
            row.value = cursor.value
            row.schema_fields = schema_fields
            job = TenantScopedRepository(session, ctx.tenant_id).get(IngestionJob, job_id)
            if job is not None:
                job.rows_read = rows_read
                job.rows_written = rows_written
                job.rows_skipped = rows_skipped
                job.cursor_value = cursor.value
                job.schema_drift = drift
            for result in report.results:
                session.add(
                    QualityResult(
                        id=new_ulid(),
                        tenant_id=ctx.tenant_id,
                        job_id=job_id,
                        rule_id=result.rule_id,
                        dataset_id=dataset_id,
                        passed=result.passed,
                        checked_rows=result.checked_rows,
                        failed_rows=result.failed_rows,
                        details={**result.details, "rule_type": result.rule_type, "severity": result.severity},
                    )
                )
            session.commit()

    def _finish(
        self,
        ctx: TenantContext,
        job_id: str,
        *,
        status: str,
        rows_read: int,
        rows_written: int,
        rows_skipped: int,
        cursor: ConnectorCursor,
        drift: list[dict[str, Any]],
        error: str | None = None,
    ) -> None:
        with self._session_factory() as session:
            job = TenantScopedRepository(session, ctx.tenant_id).get(IngestionJob, job_id)
            if job is None:
                return
            job.status = status
            job.rows_read = rows_read
            job.rows_written = rows_written
            job.rows_skipped = rows_skipped
            job.cursor_value = cursor.value
            job.schema_drift = drift
            job.error = error
            job.finished_at = utcnow_naive() if status != "running" else None
            if status == "failed":
                existing = session.scalar(
                    select(IngestionDeadLetter).where(
                        IngestionDeadLetter.tenant_id == ctx.tenant_id,
                        IngestionDeadLetter.job_id == job.id,
                    )
                )
                if existing is None:
                    session.add(
                        IngestionDeadLetter(
                            id=new_ulid(),
                            tenant_id=ctx.tenant_id,
                            job_id=job.id,
                            connector_id=job.connector_id,
                            reason=(error or "sync failed")[:1024],
                            payload={
                                "dataset_id": job.dataset_id,
                                "idempotency_key": job.idempotency_key,
                                "cursor_value": job.cursor_value,
                                "rows_read": rows_read,
                                "rows_written": rows_written,
                                "rows_skipped": rows_skipped,
                                "transform": job.transform,
                                "dedupe_key": job.dedupe_key,
                                "error": error,
                            },
                            attempts=1,
                            replayed=False,
                        )
                    )
            session.commit()


def _dead_letter_view(row: IngestionDeadLetter) -> dict[str, Any]:
    return {
        "id": row.id,
        "job_id": row.job_id,
        "connector_id": row.connector_id,
        "reason": row.reason,
        "payload": row.payload or {},
        "attempts": row.attempts,
        "replayed": row.replayed,
        "created_at": row.created_at,
    }


__all__ = ["IngestionService"]
