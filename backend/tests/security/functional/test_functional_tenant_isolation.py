"""Functional test isolation: runs and suites are tenant scoped."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.context import TenantContext
from app.core.db import Base, make_session_factory
from app.core.errors import NotFoundError
from app.modules.functional import models as functional_models
from app.modules.functional import public as functional_public
from app.modules.functional.evidence import InMemoryEvidenceWriter
from app.modules.functional.public import BrowserResult, StepSpec
from app.modules.functional.service import FunctionalTestService

_TABLES = [
    functional_models.FunctionalTestCase.__table__,
    functional_models.FunctionalTestSuite.__table__,
    functional_models.TestRun.__table__,
    functional_models.TestStep.__table__,
    functional_models.AssertionRecord.__table__,
    functional_models.FunctionalDeadLetter.__table__,
    functional_models.VisualDiff.__table__,
]


class Browser:
    def run(self, *, step, allow_hosts, timeout_seconds) -> BrowserResult:
        return BrowserResult(status_code=200)


def test_other_tenant_cannot_read_run() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine, tables=_TABLES)
    factory: sessionmaker[Session] = make_session_factory(engine)
    try:
        service = FunctionalTestService(factory, browser=Browser(), evidence=InMemoryEvidenceWriter())
        tenant_a = TenantContext(tenant_id="tenant-a", subject_id="a")
        tenant_b = TenantContext(tenant_id="tenant-b", subject_id="b")
        case = service.create_test_case(
            tenant_a,
            functional_public.TestCaseSpec(name="case", steps=(StepSpec(index=0, name="step", kind="api"),)),
        )
        suite = service.create_test_suite(tenant_a, name="suite", case_ids=[case.id])
        run_id = service.start_run(tenant_a, suite.id)

        with pytest.raises(NotFoundError):
            service.get_run(tenant_b, run_id)
        with pytest.raises(NotFoundError):
            service.start_run(tenant_b, suite.id)
    finally:
        engine.dispose()
