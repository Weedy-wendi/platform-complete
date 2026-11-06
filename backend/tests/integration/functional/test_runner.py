"""Functional runner: assertions, evidence, browser sandbox and isolation."""

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
from app.modules.functional.public import (
    AssertionSpec,
    BrowserResult,
    BrowserTimeoutError,
    HttpRequestSpec,
    HttpResponse,
    StepSpec,
)
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


class FakeHttp:
    def __init__(self, response: HttpResponse | None = None, error: Exception | None = None) -> None:
        self.response = response or HttpResponse(status_code=200, body={"ok": True}, duration_ms=5)
        self.error = error
        self.calls: list[HttpRequestSpec] = []

    def execute(self, request: HttpRequestSpec) -> HttpResponse:
        self.calls.append(request)
        if self.error is not None:
            raise self.error
        return self.response


class FakeBrowser:
    browser_version = "chromium-test"

    def __init__(self, result: BrowserResult | None = None, error: Exception | None = None) -> None:
        self.result = result or BrowserResult(
            status_code=200,
            body={"title": "ok"},
            duration_ms=4,
            screenshot=b"png-bytes",
            console=({"level": "info", "text": "hello"},),
            evidence_refs={"trace": "trace-ref"},
        )
        self.error = error
        self.calls: list[tuple[StepSpec, tuple[str, ...], float]] = []

    def run(self, *, step: StepSpec, allow_hosts: tuple[str, ...], timeout_seconds: float) -> BrowserResult:
        self.calls.append((step, allow_hosts, timeout_seconds))
        if self.error is not None:
            raise self.error
        return self.result


@pytest.fixture()
def factory() -> sessionmaker[Session]:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine, tables=_TABLES)
    try:
        yield make_session_factory(engine)
    finally:
        engine.dispose()


@pytest.fixture()
def ctx() -> TenantContext:
    return TenantContext(tenant_id="tenant-a", subject_id="user:1")


@pytest.fixture()
def evidence() -> InMemoryEvidenceWriter:
    return InMemoryEvidenceWriter()


def _service(factory, evidence, *, http=None, browser=None) -> FunctionalTestService:
    return FunctionalTestService(
        factory,
        browser=browser or FakeBrowser(),
        http=http or FakeHttp(),
        evidence=evidence,
    )


def _case(service: FunctionalTestService, ctx: TenantContext, steps: tuple[StepSpec, ...]) -> str:
    case = service.create_test_case(ctx, functional_public.TestCaseSpec(name="case", steps=steps))
    return case.id


def _run(
    service: FunctionalTestService,
    ctx: TenantContext,
    steps: tuple[StepSpec, ...],
):
    case_id = _case(service, ctx, steps)
    suite = service.create_test_suite(ctx, name="suite", case_ids=[case_id])
    run_id = service.start_run(ctx, suite.id)
    return suite, service.get_run(ctx, run_id)


def test_api_assertion_pass_and_evidence(factory, evidence, ctx) -> None:
    service = _service(factory, evidence)
    suite, view = _run(
        service,
        ctx,
        (
            StepSpec(
                index=0,
                name="GET /health",
                kind="api",
                request={"method": "GET", "url": "https://api.test/health"},
                assertions=(
                    AssertionSpec("status_code", {"equals": 200}),
                    AssertionSpec("json_path", {"path": "$.ok", "equals": True}),
                    AssertionSpec("duration_ms", {"max": 1000}),
                ),
            ),
        ),
    )

    assert view.status == "succeeded"
    assert view.suite_id == suite.id
    assert view.suite_version == "1"
    assert len(view.steps) == 1
    step = view.steps[0]
    assert step.status == "passed"
    assert step.evidence_ref is not None
    assert evidence.get(step.evidence_ref) is not None


def test_api_assertion_failure_keeps_response_evidence(factory, evidence, ctx) -> None:
    service = _service(factory, evidence)
    _, view = _run(
        service,
        ctx,
        (
            StepSpec(
                index=0,
                name="wrong status",
                kind="api",
                request={"url": "https://api.test/health"},
                assertions=(AssertionSpec("status_code", {"equals": 201}),),
            ),
        ),
    )

    assert view.status == "failed"
    assert view.steps[0].status == "failed"
    assert view.steps[0].evidence_ref is not None
    assert evidence.get(view.steps[0].evidence_ref) == {
        "status_code": 200,
        "body": {"ok": True},
        "duration_ms": 5,
    }


def test_api_executor_error_is_evidence_backed(factory, evidence, ctx) -> None:
    service = _service(factory, evidence, http=FakeHttp(error=RuntimeError("connection refused")))
    _, view = _run(
        service,
        ctx,
        (
            StepSpec(
                index=0,
                name="down",
                kind="api",
                request={"url": "https://api.test/health"},
            ),
        ),
    )

    assert view.status == "failed"
    assert view.steps[0].status == "error"
    assert view.steps[0].evidence_ref is not None
    assert evidence.get(view.steps[0].evidence_ref)["error"] == "connection refused"


def test_browser_success_collects_screenshot_evidence(factory, evidence, ctx) -> None:
    service = _service(factory, evidence)
    _, view = _run(
        service,
        ctx,
        (
            StepSpec(
                index=0,
                name="open page",
                kind="browser",
                request={"url": "https://app.test/"},
                assertions=(AssertionSpec("status_code", {"equals": 200}),),
            ),
        ),
    )

    assert view.status == "succeeded"
    step = view.steps[0]
    assert step.status == "passed"
    assert step.evidence_ref is not None
    assert evidence.get(step.evidence_ref) == b"png-bytes"


def test_browser_timeout_marks_run_failed(factory, evidence, ctx) -> None:
    browser = FakeBrowser(error=BrowserTimeoutError("browser timed out"))
    service = _service(factory, evidence, browser=browser)
    _, view = _run(
        service,
        ctx,
        (
            StepSpec(
                index=0,
                name="hang",
                kind="browser",
                request={"url": "https://app.test/"},
                timeout_seconds=1.0,
            ),
        ),
    )

    assert view.status == "failed"
    assert view.steps[0].status == "failed"
    assert view.steps[0].evidence_ref is not None


def test_browser_network_allowlist_blocks_outside_host(factory, evidence, ctx) -> None:
    browser = FakeBrowser()
    service = _service(factory, evidence, browser=browser)
    _, view = _run(
        service,
        ctx,
        (
            StepSpec(
                index=0,
                name="escape",
                kind="browser",
                request={"url": "https://evil.test/"},
                allow_hosts=("app.test",),
            ),
        ),
    )

    assert view.status == "failed"
    assert view.steps[0].status == "error"
    assert browser.calls == []


def test_cross_tenant_run_and_suite_are_not_found(factory, evidence) -> None:
    tenant_a = TenantContext(tenant_id="tenant-a", subject_id="user:1")
    tenant_b = TenantContext(tenant_id="tenant-b", subject_id="user:2")
    service = _service(factory, evidence)
    case_id = _case(service, tenant_a, (StepSpec(index=0, name="ok", kind="api"),))
    suite = service.create_test_suite(tenant_a, name="suite", case_ids=[case_id])
    run_id = service.start_run(tenant_a, suite.id)

    with pytest.raises(NotFoundError):
        service.get_run(tenant_b, run_id)
    with pytest.raises(NotFoundError):
        service.start_run(tenant_b, suite.id)


def test_visual_diff_record_persists(factory, evidence, ctx) -> None:
    from app.modules.functional.visual import ImageData

    service = _service(factory, evidence)
    row_id = service.record_visual_diff(
        ctx,
        run_id=None,
        step_id=None,
        expected_ref="artifact-1",
        actual_ref="artifact-2",
        threshold=0.01,
        expected=ImageData(1, 1, (0,)),
        actual=ImageData(1, 1, (255,)),
    )
    assert row_id
