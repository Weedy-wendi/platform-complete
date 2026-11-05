"""100k sample bulk-write benchmark (CAT-04).

Opt-in because the default suite stays fast:
    PINGCE_RUN_PERF=1 pytest tests/performance/catalog -q
"""

from __future__ import annotations

import os
import time

import pytest
from sqlalchemy import create_engine

from app.core.context import TenantContext
from app.core.db import Base, make_session_factory
from app.modules.catalog.models import Dataset, DatasetVersion, Project, Sample
from app.modules.catalog.service import CatalogService

pytestmark = pytest.mark.skipif(
    os.environ.get("PINGCE_RUN_PERF") != "1",
    reason="set PINGCE_RUN_PERF=1 to run the 100k benchmark",
)


def test_publish_100k_samples() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(
        engine,
        tables=[Project.__table__, Dataset.__table__, DatasetVersion.__table__, Sample.__table__],
    )
    factory = make_session_factory(engine)
    service = CatalogService(factory)
    ctx = TenantContext(tenant_id="tenant-a", subject_id="bench", scopes=frozenset(), trace_id="trace")
    project = service.create_project(ctx, "Bench")
    dataset = service.create_dataset(ctx, project_id=project.id, name="Large")

    samples = [
        {"sample_key": str(index), "payload": {"q": f"question {index}", "a": "answer"}} for index in range(100_000)
    ]
    started = time.perf_counter()
    ref = service.publish_version(ctx, dataset.id, samples)
    elapsed = time.perf_counter() - started
    assert service.get_version(ctx, ref).row_count == 100_000
    assert elapsed < 300, f"bulk insert took {elapsed:.1f}s"
    engine.dispose()
