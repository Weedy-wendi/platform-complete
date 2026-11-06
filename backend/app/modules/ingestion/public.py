"""Public ingestion contract.

Only protocols, immutable DTOs and the SPI live here. The concrete service is
implemented in :mod:`app.modules.ingestion.service`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol

from app.core.context import TenantContext


@dataclass(frozen=True)
class ConnectorField:
    """One inferred field of an external source."""

    name: str
    data_type: str = "string"
    nullable: bool = True


@dataclass(frozen=True)
class ConnectorCursor:
    """Opaque sync position returned by a connector.

    ``value`` is connector specific (row offset, page number, ...). ``None``
    means the connector is exhausted.
    """

    value: str | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True)
class ConnectorDescriptor:
    """Public view of a registered connector."""

    id: str
    tenant_id: str
    name: str
    kind: str
    config: dict[str, Any] = field(default_factory=dict)
    transform: dict[str, Any] | None = None
    dedupe_key: str | None = None
    secret_ref: str | None = None
    status: str = "active"


class Connector(Protocol):
    """Connector SPI (ING-01)."""

    def discover(self) -> list[ConnectorField]: ...

    def read(self, cursor: ConnectorCursor, limit: int) -> tuple[list[dict[str, Any]], ConnectorCursor]: ...


class StorageReader(Protocol):
    """Object-storage SPI used by the OSS/S3 connector (ING-11).

    Implementations return the raw (possibly compressed) object bytes for a
    key; archive/encoding handling lives in the connector so local files and
    object storage behave identically.
    """

    def read_bytes(self, key: str) -> bytes: ...

    def exists(self, key: str) -> bool: ...


@dataclass(frozen=True)
class SyncResult:
    job_id: str
    rows_read: int
    rows_written: int
    rows_skipped: int
    next_cursor: ConnectorCursor


@dataclass(frozen=True)
class SchemaDrift:
    """Difference between the stored schema and the current batch schema."""

    added: tuple[str, ...] = ()
    removed: tuple[str, ...] = ()
    changed: tuple[tuple[str, str, str], ...] = ()

    @property
    def has_drift(self) -> bool:
        return bool(self.added or self.removed or self.changed)

    def alerts(self) -> list[dict[str, Any]]:
        alerts: list[dict[str, Any]] = []
        alerts.extend({"kind": "field_added", "field": name} for name in self.added)
        alerts.extend({"kind": "field_removed", "field": name} for name in self.removed)
        alerts.extend(
            {"kind": "field_type_changed", "field": name, "from": old, "to": new} for name, old, new in self.changed
        )
        return alerts


@dataclass(frozen=True)
class QualityRuleSpec:
    rule_id: str
    rule_type: str
    config: dict[str, Any] = field(default_factory=dict)
    severity: str = "error"


@dataclass(frozen=True)
class QualityCheckResult:
    rule_id: str
    rule_type: str
    passed: bool
    checked_rows: int
    failed_rows: int
    details: dict[str, Any] = field(default_factory=dict)
    severity: str = "error"


@dataclass(frozen=True)
class QualityReport:
    results: tuple[QualityCheckResult, ...] = ()

    @property
    def passed(self) -> bool:
        return all(result.passed for result in self.results)

    @property
    def failed(self) -> tuple[QualityCheckResult, ...]:
        return tuple(result for result in self.results if not result.passed)


@dataclass(frozen=True)
class QualityResultView:
    id: str
    job_id: str
    rule_id: str | None
    dataset_id: str | None
    passed: bool
    checked_rows: int
    failed_rows: int
    details: dict[str, Any] = field(default_factory=dict)
    created_at: datetime | None = None


class SampleWriter(Protocol):
    """Callback used to write a batch into catalog-like sample structures.

    Ingestion never imports catalog internals; the adapter is injected by the
    caller. ``rollback_batch`` is invoked when a batch fails after the write
    call, so partial batches never survive.
    """

    def write_batch(
        self,
        *,
        tenant_id: str,
        dataset_id: str,
        idempotency_key: str,
        rows: list[dict[str, Any]],
    ) -> int: ...

    def rollback_batch(
        self,
        *,
        tenant_id: str,
        dataset_id: str,
        idempotency_key: str,
    ) -> None: ...


class CancellationSignal(Protocol):
    def is_set(self) -> bool: ...


class IngestionService(Protocol):
    """Public ingestion use cases."""

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
    ) -> ConnectorDescriptor: ...

    def sync(
        self,
        ctx: TenantContext,
        *,
        connector_id: str,
        dataset_id: str,
        writer: SampleWriter,
        idempotency_key: str,
        rules: tuple[QualityRuleSpec, ...] = (),
        batch_size: int = 100,
        cancel: CancellationSignal | None = None,
        transform: dict[str, Any] | None = None,
        dedupe_key: str | None = None,
    ) -> SyncResult: ...

    def quality_results(self, ctx: TenantContext, job_id: str) -> list[QualityResultView]: ...

    def dead_letters(self, ctx: TenantContext) -> list[dict[str, Any]]: ...

    def replay_dead_letter(self, ctx: TenantContext, letter_id: str) -> str: ...


__all__ = [
    "CancellationSignal",
    "Connector",
    "ConnectorCursor",
    "ConnectorDescriptor",
    "ConnectorField",
    "IngestionService",
    "QualityCheckResult",
    "QualityReport",
    "QualityResultView",
    "QualityRuleSpec",
    "SampleWriter",
    "SchemaDrift",
    "StorageReader",
    "SyncResult",
]
