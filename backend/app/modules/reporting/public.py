"""Public reporting surface."""

from app.modules.reporting.render import (
    comparison_payload,
    content_hash,
    render_comparison_json,
    render_comparison_markdown,
    render_run_json,
    render_run_markdown,
    run_payload,
)
from app.modules.reporting.service import ReportEvaluationReader, ReportReader, ReportService
from app.modules.reporting.types import ComparisonReport, ReadModelView, RunReport, ShareTarget

__all__ = [
    "ComparisonReport",
    "ReadModelView",
    "ReportEvaluationReader",
    "ReportReader",
    "ReportService",
    "RunReport",
    "ShareTarget",
    "comparison_payload",
    "content_hash",
    "render_comparison_json",
    "render_comparison_markdown",
    "render_run_json",
    "render_run_markdown",
    "run_payload",
]
