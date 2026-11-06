"""Reporting integration fixtures."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine

from app.core.context import TenantContext
from app.core.db import Base, make_session_factory
from app.modules.evaluation.models import (
    Baseline,
    EvalSuite,
    Evaluator,
    EvaluatorVersion,
    JudgeCall,
    Metric,
    Run,
    RunItem,
    Score,
    SuiteVersion,
    Target,
)
from app.modules.evaluation.service import EvaluationService
from app.modules.reporting.models import ReadModelRun, ReportSnapshot
from app.modules.reporting.service import ReportReader, ReportService

TABLES = [
    Evaluator.__table__,
    EvaluatorVersion.__table__,
    Metric.__table__,
    EvalSuite.__table__,
    SuiteVersion.__table__,
    Target.__table__,
    Run.__table__,
    RunItem.__table__,
    Score.__table__,
    JudgeCall.__table__,
    Baseline.__table__,
    ReportSnapshot.__table__,
    ReadModelRun.__table__,
]


@pytest.fixture()
def factory():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine, tables=TABLES)
    try:
        yield make_session_factory(engine)
    finally:
        engine.dispose()


@pytest.fixture()
def ctx() -> TenantContext:
    return TenantContext(tenant_id="tenant-a", subject_id="user:1", scopes=frozenset(), trace_id="trace-1")


@pytest.fixture()
def evaluation(factory) -> EvaluationService:
    return EvaluationService(factory, max_workers=1)


@pytest.fixture()
def reports(factory, evaluation) -> ReportService:
    return ReportService(factory, evaluation=evaluation)


@pytest.fixture()
def reader(factory, evaluation) -> ReportReader:
    return ReportReader(factory, evaluation=evaluation)
