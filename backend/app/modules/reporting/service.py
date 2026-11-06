"""Report generation, immutable snapshots, export and signed share links."""

from __future__ import annotations

import base64
import csv
import hashlib
import hmac
import io
import json
import time
from collections.abc import Iterable
from dataclasses import asdict
from typing import Protocol
from xml.etree import ElementTree

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.core.clock import utcnow_naive
from app.core.context import TenantContext
from app.core.errors import InvalidArgumentError, NotFoundError
from app.core.ids import new_ulid
from app.core.pagination import Page
from app.modules.evaluation.public import (
    ComparisonView,
    RunItemQuery,
    RunItemView,
    RunReader,
    RunView,
)
from app.modules.reporting.models import ReadModelRun, ReportSnapshot
from app.modules.reporting.render import (
    comparison_payload,
    content_hash,
    render_comparison_json,
    render_comparison_markdown,
    render_run_json,
    render_run_markdown,
)
from app.modules.reporting.types import ComparisonReport, ReadModelView, RunReport, ShareTarget

_PAGE_SIZE = 100


class ReportEvaluationReader(Protocol):
    def get_run(self, ctx: TenantContext, run_id: str) -> RunView: ...
    def list_items(self, ctx: TenantContext, run_id: str, query: RunItemQuery) -> Page[RunItemView]: ...
    def compare(
        self, ctx: TenantContext, run_a: str, run_b: str, metric_names: list[str] | None = None
    ) -> ComparisonView: ...


class ReportService:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        evaluation: ReportEvaluationReader | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._evaluation = evaluation or RunReader(session_factory)

    # Read model ------------------------------------------------------------

    def refresh_read_model(self, ctx: TenantContext, run_id: str) -> ReadModelView:
        run = self._evaluation.get_run(ctx, run_id)
        metrics = [asdict(summary) for summary in run.metrics]
        with self._session_factory() as session:
            row = session.scalar(
                select(ReadModelRun).where(ReadModelRun.tenant_id == ctx.tenant_id, ReadModelRun.run_id == run_id)
            )
            if row is None:
                row = ReadModelRun(
                    id=new_ulid(),
                    tenant_id=ctx.tenant_id,
                    run_id=run_id,
                    manifest_hash=run.manifest_hash,
                    status=run.status,
                    metrics=metrics,
                    total_items=run.total_items,
                    succeeded_items=run.succeeded_items,
                    failed_items=run.failed_items,
                    skipped_items=run.skipped_items,
                    cost_usd=run.cost_usd,
                )
                session.add(row)
            else:
                row.manifest_hash = run.manifest_hash
                row.status = run.status
                row.metrics = metrics
                row.total_items = run.total_items
                row.succeeded_items = run.succeeded_items
                row.failed_items = run.failed_items
                row.skipped_items = run.skipped_items
                row.cost_usd = run.cost_usd
                row.updated_at = utcnow_naive()
            session.commit()
            return _read_model_view(row)

    def get_read_model(self, ctx: TenantContext, run_id: str) -> ReadModelView:
        with self._session_factory() as session:
            row = session.scalar(
                select(ReadModelRun).where(ReadModelRun.tenant_id == ctx.tenant_id, ReadModelRun.run_id == run_id)
            )
            if row is None:
                raise NotFoundError("Run read model not found")
            return _read_model_view(row)

    # Run reports -----------------------------------------------------------

    def generate_run_report(self, ctx: TenantContext, run_id: str, fmt: str = "json") -> RunReport:
        if fmt not in {"json", "markdown"}:
            raise InvalidArgumentError("unsupported report format", format=fmt)
        run = self._evaluation.get_run(ctx, run_id)
        with self._session_factory() as session:
            snapshot = session.scalar(
                select(ReportSnapshot).where(
                    ReportSnapshot.tenant_id == ctx.tenant_id,
                    ReportSnapshot.run_id == run_id,
                    ReportSnapshot.manifest_hash == run.manifest_hash,
                    ReportSnapshot.format == fmt,
                )
            )
            if snapshot is not None:
                return _run_report(snapshot)
            items = self._load_items(ctx, run_id)
            content = self._render(run, items, fmt)
            snapshot = ReportSnapshot(
                id=new_ulid(),
                tenant_id=ctx.tenant_id,
                run_id=run_id,
                manifest_hash=run.manifest_hash,
                format=fmt,
                content=content,
                content_hash=content_hash(content),
            )
            session.add(snapshot)
            try:
                session.commit()
            except IntegrityError:
                session.rollback()
                snapshot = session.scalar(
                    select(ReportSnapshot).where(
                        ReportSnapshot.tenant_id == ctx.tenant_id,
                        ReportSnapshot.run_id == run_id,
                        ReportSnapshot.manifest_hash == run.manifest_hash,
                        ReportSnapshot.format == fmt,
                    )
                )
                if snapshot is None:
                    raise
            return _run_report(snapshot)

    def get_run_report(self, ctx: TenantContext, run_id: str, fmt: str = "json") -> RunReport:
        return self.generate_run_report(ctx, run_id, fmt)

    def comparison(self, ctx: TenantContext, run_a: str, run_b: str) -> ComparisonReport:
        return self.compare_report(ctx, run_a, run_b)

    def compare_report(self, ctx: TenantContext, run_a: str, run_b: str) -> ComparisonReport:
        comparison = self._evaluation.compare(ctx, run_a, run_b)
        return ComparisonReport(
            run_a=run_a,
            run_b=run_b,
            metrics=[asdict(metric) for metric in comparison.metrics],
            regressions=[asdict(metric) for metric in comparison.regressions],
            improvements=[asdict(metric) for metric in comparison.improvements],
            warnings=list(comparison.warnings),
        )

    def render_comparison(self, ctx: TenantContext, run_a: str, run_b: str, fmt: str = "markdown") -> str:
        comparison = self._evaluation.compare(ctx, run_a, run_b)
        if fmt == "json":
            return render_comparison_json(comparison)
        if fmt == "markdown":
            return render_comparison_markdown(comparison)
        raise InvalidArgumentError("unsupported comparison format", format=fmt)

    # Export ----------------------------------------------------------------

    def export(self, ctx: TenantContext, run_id: str, fmt: str = "json") -> bytes:
        run = self._evaluation.get_run(ctx, run_id)
        if fmt == "json":
            return self._render(run, self._load_items(ctx, run_id), "json").encode("utf-8")
        items = self._load_items(ctx, run_id)
        if fmt == "csv":
            return self._export_csv(run, items)
        if fmt == "junit":
            return self._export_junit(run, items)
        raise InvalidArgumentError("unsupported export format", format=fmt)

    def export_comparison(
        self,
        ctx: TenantContext,
        run_id: str,
        baseline_run_id: str,
        fmt: str = "json",
    ) -> bytes:
        """Export a baseline/candidate comparison as JSON, CSV or JUnit."""

        if fmt not in {"json", "csv", "junit"}:
            raise InvalidArgumentError("unsupported comparison export format", format=fmt)
        comparison = self._evaluation.compare(ctx, baseline_run_id, run_id)
        if fmt == "json":
            return render_comparison_json(comparison).encode("utf-8")
        if fmt == "csv":
            return self._export_comparison_csv(comparison)
        return self._export_comparison_junit(comparison)

    def iter_export(self, ctx: TenantContext, run_id: str, fmt: str = "csv") -> Iterable[bytes]:
        """Line-oriented export for large runs (CSV only)."""

        if fmt != "csv":
            yield self.export(ctx, run_id, fmt)
            return
        run = self._evaluation.get_run(ctx, run_id)
        yield _csv_header()
        yield _csv_run_rows(run)
        for item in self._load_items(ctx, run_id):
            yield _csv_item_rows(item)

    # Share links -----------------------------------------------------------

    def create_share_link(
        self,
        ctx: TenantContext,
        run_id: str,
        *,
        secret: str,
        fmt: str = "markdown",
        ttl_seconds: int = 3600,
        now: float | None = None,
    ) -> str:
        if not secret:
            raise InvalidArgumentError("share link secret is required")
        if ttl_seconds <= 0:
            raise InvalidArgumentError("share link ttl must be positive")
        self._evaluation.get_run(ctx, run_id)
        payload = {
            "tenant_id": ctx.tenant_id,
            "run_id": run_id,
            "format": fmt,
            "expires_at": int((now if now is not None else time.time()) + ttl_seconds),
        }
        encoded = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode()
        signature = hmac.new(secret.encode(), encoded.encode(), hashlib.sha256).hexdigest()[:32]
        return f"{encoded}.{signature}"

    def read_share_link(self, token: str, *, secret: str, now: float | None = None) -> ShareTarget:
        if not secret:
            raise InvalidArgumentError("share link secret is required")
        try:
            encoded, signature = token.split(".", 1)
        except ValueError as exc:
            raise InvalidArgumentError("invalid share link") from exc
        expected = hmac.new(secret.encode(), encoded.encode(), hashlib.sha256).hexdigest()[:32]
        if not hmac.compare_digest(expected, signature):
            raise InvalidArgumentError("invalid share link signature")
        try:
            payload = json.loads(base64.urlsafe_b64decode(encoded.encode()))
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            raise InvalidArgumentError("invalid share link") from exc
        expires_at = int(payload.get("expires_at", 0))
        if expires_at < int(now if now is not None else time.time()):
            raise InvalidArgumentError("share link has expired")
        return ShareTarget(
            tenant_id=str(payload.get("tenant_id") or ""),
            run_id=str(payload.get("run_id") or ""),
            format=str(payload.get("format") or "markdown"),
            expires_at=expires_at,
        )

    def resolve_share_link(
        self,
        ctx: TenantContext,
        token: str,
        *,
        secret: str,
        now: float | None = None,
    ) -> ShareTarget:
        target = self.read_share_link(token, secret=secret, now=now)
        if target.tenant_id != ctx.tenant_id:
            raise NotFoundError("Report not found")
        return target

    # Internals -------------------------------------------------------------

    def _load_items(self, ctx: TenantContext, run_id: str) -> list[RunItemView]:
        items: list[RunItemView] = []
        cursor: str | None = None
        for _ in range(10_000):
            page = self._evaluation.list_items(ctx, run_id, RunItemQuery(cursor=cursor, limit=_PAGE_SIZE))
            items.extend(page.items)
            if not page.next_cursor:
                return items
            cursor = page.next_cursor
        raise InvalidArgumentError("run has too many items for a single report")

    @staticmethod
    def _render(run: RunView, items: list[RunItemView], fmt: str) -> str:
        return render_run_json(run, items) if fmt == "json" else render_run_markdown(run, items)

    @staticmethod
    def _export_csv(run: RunView, items: list[RunItemView]) -> bytes:
        buffer = io.StringIO()
        buffer.write(_csv_header().decode("utf-8"))
        buffer.write(_csv_run_rows(run).decode("utf-8"))
        for item in items:
            buffer.write(_csv_item_rows(item).decode("utf-8"))
        return buffer.getvalue().encode("utf-8")

    @staticmethod
    def _export_junit(run: RunView, items: list[RunItemView]) -> bytes:
        suite = ElementTree.Element(
            "testsuite",
            {
                "name": f"run-{run.run_id}",
                "tests": str(len(items)),
                "failures": str(sum(1 for item in items if item.status == "failed")),
                "errors": "0",
                "skipped": str(sum(1 for item in items if item.status == "skipped")),
            },
        )
        for item in items:
            case = ElementTree.SubElement(
                suite,
                "testcase",
                {
                    "name": item.sample_key,
                    "classname": run.run_id,
                    "time": f"{item.latency_ms / 1000:.3f}",
                },
            )
            if item.status == "failed":
                failure = ElementTree.SubElement(case, "failure", {"message": item.error or "item failed"})
                failure.text = item.error or "item failed"
            if item.scores:
                output = ElementTree.SubElement(case, "system-out")
                output.text = json.dumps(
                    {score.metric_name: score.value for score in item.scores},
                    sort_keys=True,
                    ensure_ascii=False,
                )
        return ElementTree.tostring(suite, encoding="utf-8", xml_declaration=True)

    @staticmethod
    def _export_comparison_csv(comparison: ComparisonView) -> bytes:
        payload = comparison_payload(comparison)
        buffer = io.StringIO()
        writer = csv.writer(buffer, lineterminator="\n")
        writer.writerow(["section", "key", "value"])
        writer.writerow(["comparison", "run_a", payload["run_a"]])
        writer.writerow(["comparison", "run_b", payload["run_b"]])
        writer.writerow(["comparison", "comparable", payload["comparable"]])
        for metric in payload["metrics"]:
            prefix = f"metric.{metric['name']}"
            writer.writerow(["metric", f"{prefix}.baseline", metric["baseline"]])
            writer.writerow(["metric", f"{prefix}.candidate", metric["candidate"]])
            writer.writerow(["metric", f"{prefix}.delta", metric["delta"]])
            writer.writerow(["metric", f"{prefix}.delta_pct", metric["delta_pct"]])
            writer.writerow(["metric", f"{prefix}.significant", metric["significant"]])
            writer.writerow(["metric", f"{prefix}.ci_low", metric["ci_low"]])
            writer.writerow(["metric", f"{prefix}.ci_high", metric["ci_high"]])
        for index, warning in enumerate(payload["warnings"]):
            writer.writerow(["warning", str(index), warning])
        return buffer.getvalue().encode("utf-8")

    @staticmethod
    def _export_comparison_junit(comparison: ComparisonView) -> bytes:
        payload = comparison_payload(comparison)
        regressions = {metric["name"] for metric in payload["regressions"]}
        suite = ElementTree.Element(
            "testsuite",
            {
                "name": f"comparison-{payload['run_a']}-{payload['run_b']}",
                "tests": str(len(payload["metrics"])),
                "failures": str(len(payload["regressions"])),
                "errors": "0",
                "skipped": "0",
            },
        )
        for metric in payload["metrics"]:
            case = ElementTree.SubElement(
                suite,
                "testcase",
                {
                    "name": str(metric["name"]),
                    "classname": str(payload["run_b"]),
                    "time": "0.000",
                },
            )
            if metric["name"] in regressions:
                message = f"{metric['name']} regressed by {metric['delta_pct']:.4f}%"
                failure = ElementTree.SubElement(case, "failure", {"message": message})
                failure.text = message
            output = ElementTree.SubElement(case, "system-out")
            output.text = json.dumps(metric, sort_keys=True, ensure_ascii=False)
        if payload["warnings"]:
            errors = ElementTree.SubElement(suite, "system-err")
            errors.text = "\n".join(str(warning) for warning in payload["warnings"])
        return ElementTree.tostring(suite, encoding="utf-8", xml_declaration=True)


class ReportReader:
    """Read-only facade. It renders a transient report when no snapshot exists."""

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        evaluation: ReportEvaluationReader | None = None,
    ) -> None:
        self._service = ReportService(session_factory, evaluation=evaluation)
        self._evaluation = evaluation or RunReader(session_factory)
        self._session_factory = session_factory

    def get_run_report(self, ctx: TenantContext, run_id: str, fmt: str = "json") -> RunReport:
        if fmt not in {"json", "markdown"}:
            raise InvalidArgumentError("unsupported report format", format=fmt)
        run = self._evaluation.get_run(ctx, run_id)
        with self._session_factory() as session:
            snapshot = session.scalar(
                select(ReportSnapshot).where(
                    ReportSnapshot.tenant_id == ctx.tenant_id,
                    ReportSnapshot.run_id == run_id,
                    ReportSnapshot.manifest_hash == run.manifest_hash,
                    ReportSnapshot.format == fmt,
                )
            )
            if snapshot is not None:
                return _run_report(snapshot)
        items = self._service._load_items(ctx, run_id)
        content = self._service._render(run, items, fmt)
        return RunReport(
            run_id=run_id,
            manifest_hash=run.manifest_hash,
            format=fmt,  # type: ignore[arg-type]
            content=content,
            generated_at=utcnow_naive(),
        )

    def compare_report(self, ctx: TenantContext, run_a: str, run_b: str) -> ComparisonReport:
        return self._service.compare_report(ctx, run_a, run_b)

    def export(self, ctx: TenantContext, run_id: str, fmt: str = "json") -> bytes:
        return self._service.export(ctx, run_id, fmt)

    def export_comparison(
        self,
        ctx: TenantContext,
        run_id: str,
        baseline_run_id: str,
        fmt: str = "json",
    ) -> bytes:
        return self._service.export_comparison(ctx, run_id, baseline_run_id, fmt)


def _run_report(row: ReportSnapshot) -> RunReport:
    return RunReport(
        run_id=row.run_id,
        manifest_hash=row.manifest_hash,
        format=row.format,  # type: ignore[arg-type]
        content=row.content,
        generated_at=row.created_at,
    )


def _read_model_view(row: ReadModelRun) -> ReadModelView:
    return ReadModelView(
        tenant_id=row.tenant_id,
        run_id=row.run_id,
        manifest_hash=row.manifest_hash,
        status=row.status,
        metrics=row.metrics,
        total_items=row.total_items,
        succeeded_items=row.succeeded_items,
        failed_items=row.failed_items,
        skipped_items=row.skipped_items,
        cost_usd=row.cost_usd,
        updated_at=row.updated_at,
    )


def _csv_header() -> bytes:
    return b"section,key,value\n"


def _csv_run_rows(run: RunView) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["run", "run_id", run.run_id])
    writer.writerow(["run", "status", run.status])
    writer.writerow(["run", "manifest_hash", run.manifest_hash])
    writer.writerow(["run", "total_items", run.total_items])
    writer.writerow(["run", "succeeded_items", run.succeeded_items])
    writer.writerow(["run", "failed_items", run.failed_items])
    for metric in run.metrics:
        writer.writerow(["metric", f"{metric.name}.value", metric.value])
        writer.writerow(["metric", f"{metric.name}.count", metric.count])
    return buffer.getvalue().encode("utf-8")


def _csv_item_rows(item: RunItemView) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["item", f"{item.sample_key}.status", item.status])
    for score in item.scores:
        writer.writerow(["item", f"{item.sample_key}.{score.metric_name}", score.value])
    return buffer.getvalue().encode("utf-8")
