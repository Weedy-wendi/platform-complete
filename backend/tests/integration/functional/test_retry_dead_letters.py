"""Single browser retry and dead-letter replay tests (FUN-08)."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine

from app.core.context import TenantContext
from app.core.db import Base, make_session_factory
from app.core.errors import InvalidArgumentError
from app.modules.functional import models as functional_models
from app.modules.functional import public as functional_public
from app.modules.functional.evidence import InMemoryEvidenceWriter
from app.modules.functional.public import BrowserResult, BrowserTimeoutError, StepSpec
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


class SequenceBrowser:
    def __init__(self, outcomes) -> None:
        self.outcomes = list(outcomes)
        self.calls = 0

    def run(self, *, step, allow_hosts, timeout_seconds) -> BrowserResult:
        self.calls += 1
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class AlwaysTimeoutBrowser:
    def __init__(self) -> None:
        self.calls = 0

    def run(self, *, step, allow_hosts, timeout_seconds) -> BrowserResult:
        self.calls += 1
        raise BrowserTimeoutError("browser timed out")


def _setup(browser):
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine, tables=_TABLES)
    factory = make_session_factory(engine)
    service = FunctionalTestService(factory, browser=browser, evidence=InMemoryEvidenceWriter())
    ctx = TenantContext(tenant_id="tenant-a", subject_id="user:1")
    case = service.create_test_case(
        ctx,
        functional_public.TestCaseSpec(
            name="browser case",
            steps=(StepSpec(index=0, name="open", kind="browser", request={"url": "https://app.test/"}),),
        ),
    )
    suite = service.create_test_suite(ctx, name="suite", case_ids=[case.id])
    return engine, service, ctx, suite


def test_timeout_then_success_uses_two_attempts() -> None:
    browser = SequenceBrowser([BrowserTimeoutError("timeout"), BrowserResult(status_code=200)])
    engine, service, ctx, suite = _setup(browser)
    try:
        run_id = service.start_run(ctx, suite.id)
        view = service.get_run(ctx, run_id)

        assert browser.calls == 2
        assert view.status == "succeeded"
        assert view.steps[0].status == "passed"
        assert view.steps[0].attempts == 2
        assert service.dead_letters(ctx) == []
    finally:
        engine.dispose()


def test_timeout_twice_records_one_dead_letter() -> None:
    browser = AlwaysTimeoutBrowser()
    engine, service, ctx, suite = _setup(browser)
    try:
        run_id = service.start_run(ctx, suite.id)
        view = service.get_run(ctx, run_id)

        assert browser.calls == 2
        assert view.status == "failed"
        assert view.steps[0].status == "failed"
        assert view.steps[0].attempts == 2

        letters = service.dead_letters(ctx)
        assert len(letters) == 1
        assert letters[0]["run_id"] == run_id
        assert letters[0]["attempts"] == 2
        assert letters[0]["replayed"] is False
    finally:
        engine.dispose()


def test_replay_returns_new_run_id() -> None:
    browser = AlwaysTimeoutBrowser()
    engine, service, ctx, suite = _setup(browser)
    try:
        original_run_id = service.start_run(ctx, suite.id)
        letter = service.dead_letters(ctx)[0]

        new_run_id = service.replay_dead_letter(ctx, letter["id"])

        assert new_run_id != original_run_id
        assert service.get_run(ctx, new_run_id).run_id == new_run_id
        assert service.dead_letters(ctx)[0]["replayed"] is True
        with pytest.raises(InvalidArgumentError):
            service.replay_dead_letter(ctx, letter["id"])
    finally:
        engine.dispose()
