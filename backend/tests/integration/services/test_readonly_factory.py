"""SQL-backed read-only services used by the deployed MCP server."""

from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy import create_engine

from app.core.config import Settings
from app.core.db import Base, make_session_factory
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
from app.services.readonly import (
    SqlBadcaseSearch,
    SqlDatasetRepository,
    SqlEvaluatorRepository,
    SqlGateReader,
    SqlProjectRepository,
    SqlRunRepository,
)

TABLES = [
    ProjectRow.__table__,
    DatasetRow.__table__,
    DatasetVersionRow.__table__,
    SampleRow.__table__,
    EvaluatorRow.__table__,
    MetricRow.__table__,
    RunRow.__table__,
    RunItemRow.__table__,
    ScoreRow.__table__,
    GateResultRecord.__table__,
]


@pytest.fixture()
def factory():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine, tables=TABLES)
    session_factory = make_session_factory(engine)
    stamp = datetime(2026, 1, 1)
    with session_factory() as session:
        session.add_all(
            [
                ProjectRow(id="p1", tenant_id="t1", name="P", created_by="test"),
                DatasetRow(
                    id="d1",
                    tenant_id="t1",
                    project_id="p1",
                    name="D",
                    latest_version=1,
                    sample_count=1,
                    tags=["gold"],
                    created_by="test",
                ),
                DatasetVersionRow(
                    id="v1",
                    tenant_id="t1",
                    dataset_id="d1",
                    version=1,
                    content_hash="hash",
                    row_count=1,
                    schema_fields=[{"name": "q", "type": "string", "nullable": False}],
                    created_by="test",
                ),
                SampleRow(
                    id="s1",
                    tenant_id="t1",
                    dataset_version_id="v1",
                    dataset_id="d1",
                    version=1,
                    sample_key="k1",
                    payload={"q": "hello", "tags": ["gold"]},
                ),
                EvaluatorRow(
                    id="e1",
                    tenant_id="t1",
                    name="E",
                    kind="rule",
                    latest_version=1,
                    created_by="test",
                ),
                MetricRow(id="m1", tenant_id="t1", name="accuracy", evaluator_id="e1"),
                RunRow(
                    id="r1",
                    tenant_id="t1",
                    client_request_id="c1",
                    suite_id="suite1",
                    dataset_id="d1",
                    dataset_version=1,
                    dataset_hash="dh",
                    manifest={"target_config": {"provider": "openai", "model": "gpt-4o-mini"}},
                    manifest_hash="mh",
                    status="succeeded",
                    total_items=2,
                    succeeded_items=1,
                    failed_items=1,
                    progress=100,
                    cost_usd=0.1,
                    created_by="test",
                    created_at=stamp,
                ),
                RunItemRow(
                    id="i1",
                    tenant_id="t1",
                    run_id="r1",
                    sample_key="k1",
                    payload={"q": "hello"},
                    status="succeeded",
                    output="hello",
                    latency_ms=10,
                    created_at=stamp,
                ),
                RunItemRow(
                    id="i2",
                    tenant_id="t1",
                    run_id="r1",
                    sample_key="k2",
                    payload={"q": "bad"},
                    status="failed",
                    error="wrong answer",
                    raw_ref="artifact://raw/i2",
                    created_at=stamp,
                ),
                ScoreRow(
                    id="sc1",
                    tenant_id="t1",
                    run_id="r1",
                    run_item_id="i1",
                    metric_name="accuracy",
                    value=1.0,
                ),
                GateResultRecord(
                    id="g1",
                    tenant_id="t1",
                    gate_id="gate1",
                    suite_id="suite1",
                    run_id="r1",
                    manifest_hash="mh",
                    passed=True,
                    status="passed",
                    rules=[
                        {
                            "name": "accuracy",
                            "expected": ">=0.8",
                            "actual": "1.0",
                            "passed": True,
                            "evidence_ref": "run://r1",
                        }
                    ],
                    evaluated_at=stamp,
                    created_at=stamp,
                ),
            ]
        )
        session.commit()
    try:
        yield session_factory, engine
    finally:
        engine.dispose()


def test_project_and_dataset_mapping(factory) -> None:
    session_factory, _ = factory
    projects = SqlProjectRepository(session_factory).list_for_tenant("t1")
    assert [project.id for project in projects] == ["p1"]
    datasets = SqlDatasetRepository(session_factory).list_for_tenant("t1")
    assert datasets[0].tags == ("gold",)
    version = SqlDatasetRepository(session_factory).get_version("t1", "d1", None)
    assert version is not None
    assert version.fields[0].name == "q"
    samples = SqlDatasetRepository(session_factory).list_samples("t1", "d1", 1)
    assert samples[0].payload["q"] == "hello"


def test_evaluator_run_and_item_mapping(factory) -> None:
    session_factory, _ = factory
    evaluators = SqlEvaluatorRepository(session_factory).list_for_tenant("t1")
    assert evaluators[0].version == "1"
    assert evaluators[0].metrics[0].name == "accuracy"
    runs = SqlRunRepository(session_factory)
    run = runs.get("t1", "r1")
    assert run is not None
    assert run.target is not None and run.target.provider == "openai"
    assert run.metrics[0].value == 1.0
    items = runs.list_items("t1", "r1")
    assert {item.status for item in items} == {"succeeded", "failed"}
    failed = next(item for item in items if item.id == "i2")
    assert failed.evidence_ref == "artifact://raw/i2"
    assert runs.get("other", "r1") is None


def test_badcase_and_gate_mapping(factory) -> None:
    session_factory, _ = factory
    result = SqlBadcaseSearch(session_factory).search_badcases(
        tenant_id="t1", query="wrong", dataset_id=None, tags=(), limit=10
    )
    assert result.degraded is True
    assert [hit.badcase.id for hit in result.hits] == ["i2"]
    gate = SqlGateReader(session_factory).read_gate(tenant_id="t1", suite_id="suite1", run_id="r1")
    assert gate is not None
    assert gate.passed is True
    assert gate.rules[0].evidence_ref == "run://r1"
    assert SqlGateReader(session_factory).read_gate(tenant_id="t1", suite_id="other", run_id="r1") is None


def test_build_readonly_services(monkeypatch, factory) -> None:
    session_factory, engine = factory
    import app.services.readonly as readonly

    monkeypatch.setattr(readonly, "create_readonly_engine_from_dsn", lambda dsn: engine)
    registry = readonly.build_readonly_services(Settings(env="test", mcp_db_dsn="sqlite://"))
    assert registry.projects.list_projects("t1")[0].id == "p1"
    assert registry.evaluation.get_run("t1", "r1").id == "r1"
