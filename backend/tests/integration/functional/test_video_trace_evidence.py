"""Browser video/trace evidence tests (FUN-07)."""

from __future__ import annotations

import json

from sqlalchemy import create_engine

from app.core.context import TenantContext
from app.core.db import Base, make_session_factory
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


class FakeBrowser:
    def __init__(self, result: BrowserResult) -> None:
        self.result = result

    def run(self, *, step, allow_hosts, timeout_seconds) -> BrowserResult:
        return self.result


def _run(result: BrowserResult, evidence: InMemoryEvidenceWriter):
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine, tables=_TABLES)
    factory = make_session_factory(engine)
    service = FunctionalTestService(factory, browser=FakeBrowser(result), evidence=evidence)
    ctx = TenantContext(tenant_id="tenant-a", subject_id="user:1")
    case = service.create_test_case(
        ctx,
        functional_public.TestCaseSpec(
            name="browser case",
            steps=(StepSpec(index=0, name="open", kind="browser", request={"url": "https://app.test/"}),),
        ),
    )
    suite = service.create_test_suite(ctx, name="suite", case_ids=[case.id])
    run_id = service.start_run(ctx, suite.id)
    view = service.get_run(ctx, run_id)
    engine.dispose()
    return view


def test_video_and_trace_are_persisted() -> None:
    evidence = InMemoryEvidenceWriter()
    trace = {
        "events": [{"type": "click", "target": "#submit"}],
        "headers": {"Authorization": "Bearer super-secret", "Cookie": "session=abc"},
    }
    view = _run(BrowserResult(status_code=200, video=b"video-bytes", trace=trace), evidence)

    step = view.steps[0]
    assert {"video", "trace"} <= set(step.evidence_refs)
    assert evidence.get(step.evidence_refs["video"]) == b"video-bytes"

    stored_trace = evidence.get(step.evidence_refs["trace"])
    assert isinstance(stored_trace, dict)
    assert stored_trace["events"] == [{"type": "click", "target": "#submit"}]
    assert stored_trace["headers"]["Authorization"] == "[REDACTED]"
    assert stored_trace["headers"]["Cookie"] == "[REDACTED]"
    assert "super-secret" not in json.dumps(stored_trace)


def test_video_and_trace_refs_are_absent_when_not_produced() -> None:
    evidence = InMemoryEvidenceWriter()
    view = _run(BrowserResult(status_code=200, evidence_refs={}), evidence)

    refs = view.steps[0].evidence_refs
    assert "video" not in refs
    assert "trace" not in refs
