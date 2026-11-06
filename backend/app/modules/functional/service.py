"""Functional test service and in-process runner (FUN-01..05)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.clock import utcnow_naive
from app.core.context import TenantContext
from app.core.errors import InvalidArgumentError, NotFoundError
from app.core.ids import new_ulid
from app.core.repository import TenantScopedRepository
from app.modules.functional.assertions import (
    AssertionOutcome,
    evaluate_assertions,
    summarize,
)
from app.modules.functional.browser import (
    BrowserSandboxConfig,
    ensure_host_allowed,
)
from app.modules.functional.evidence import InMemoryEvidenceWriter, sanitize_evidence
from app.modules.functional.http import HttpxExecutor
from app.modules.functional.models import (
    AssertionRecord,
    FunctionalDeadLetter,
    FunctionalTestCase,
    FunctionalTestSuite,
    TestRun,
    TestStep,
    VisualDiff,
)
from app.modules.functional.public import (
    AssertionSpec,
    BrowserAdapter,
    BrowserResult,
    BrowserTimeoutError,
    EvidenceWriter,
    HttpExecutor,
    HttpRequestSpec,
    NetworkPolicyError,
    StepSpec,
    TestCaseSpec,
    TestCaseView,
    TestRunView,
    TestStepResult,
    TestSuiteView,
)
from app.modules.functional.visual import ImageData, compare_images


@dataclass
class _StepOutcome:
    step_id: str
    status: str
    duration_ms: int
    assertion: str | None = None
    evidence_ref: str | None = None
    evidence_refs: dict[str, str] = field(default_factory=dict)
    error: str | None = None
    outcomes: list[AssertionOutcome] = field(default_factory=list)
    case_id: str = ""
    name: str = ""
    kind: str = ""
    step_index: int = 0
    attempts: int = 1
    dead_letter_reason: str | None = None


def _safe_json(value: Any) -> Any:
    try:
        json.dumps(value)
        return value
    except (TypeError, ValueError):
        return {"repr": str(value)}


def _step_to_dict(step: StepSpec) -> dict[str, Any]:
    return {
        "index": step.index,
        "name": step.name,
        "kind": step.kind,
        "request": step.request,
        "assertions": [{"kind": item.kind, "config": item.config} for item in step.assertions],
        "allow_hosts": list(step.allow_hosts),
        "timeout_seconds": step.timeout_seconds,
    }


def step_from_dict(data: dict[str, Any]) -> StepSpec:
    assertions = tuple(
        AssertionSpec(kind=str(item.get("kind", "")), config=dict(item.get("config") or {}))
        for item in data.get("assertions", [])
    )
    return StepSpec(
        index=int(data.get("index", 0)),
        name=str(data.get("name", "")),
        kind=str(data.get("kind", "api")),
        request=dict(data.get("request") or {}),
        assertions=assertions,
        allow_hosts=tuple(str(host) for host in data.get("allow_hosts", ())),
        timeout_seconds=float(data.get("timeout_seconds", 30.0)),
    )


class FunctionalTestService:
    """Concrete functional-test service.

    Runs execute synchronously in-process; browsers and HTTP calls are always
    injected adapters so no browser is spawned in the API process.
    """

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        browser: BrowserAdapter,
        http: HttpExecutor | None = None,
        evidence: EvidenceWriter | None = None,
        sandbox: BrowserSandboxConfig | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._browser = browser
        self._http = http or HttpxExecutor()
        self._evidence = evidence or InMemoryEvidenceWriter()
        self._sandbox = sandbox or BrowserSandboxConfig()

    # Authoring ------------------------------------------------------------

    def create_test_case(self, ctx: TenantContext, spec: TestCaseSpec) -> TestCaseView:
        if not spec.name.strip():
            raise InvalidArgumentError("test case name is required")
        for step in spec.steps:
            if not step.name.strip():
                raise InvalidArgumentError("step name is required")
            if step.kind not in {"api", "browser"}:
                raise InvalidArgumentError("step kind must be api or browser", kind=step.kind)
        with self._session_factory() as session:
            version = (
                session.scalar(
                    select(func.max(FunctionalTestCase.version)).where(
                        FunctionalTestCase.tenant_id == ctx.tenant_id,
                        FunctionalTestCase.name == spec.name.strip(),
                    )
                )
                or 0
            ) + 1
            row = FunctionalTestCase(
                id=new_ulid(),
                tenant_id=ctx.tenant_id,
                name=spec.name.strip(),
                description=spec.description,
                version=version,
                steps=[_step_to_dict(step) for step in spec.steps],
                created_by=ctx.subject_id,
            )
            session.add(row)
            session.commit()
            return _case_view(row)

    def create_test_suite(
        self,
        ctx: TenantContext,
        *,
        name: str,
        case_ids: list[str],
    ) -> TestSuiteView:
        if not name.strip():
            raise InvalidArgumentError("test suite name is required")
        if not case_ids:
            raise InvalidArgumentError("test suite requires at least one case")
        with self._session_factory() as session:
            refs: list[dict[str, Any]] = []
            for case_id in case_ids:
                case = TenantScopedRepository(session, ctx.tenant_id).get(FunctionalTestCase, case_id)
                if case is None:
                    raise NotFoundError("Test case not found", case_id=case_id)
                refs.append({"case_id": case.id, "version": case.version})
            version = (
                session.scalar(
                    select(func.max(FunctionalTestSuite.version)).where(
                        FunctionalTestSuite.tenant_id == ctx.tenant_id,
                        FunctionalTestSuite.name == name.strip(),
                    )
                )
                or 0
            ) + 1
            row = FunctionalTestSuite(
                id=new_ulid(),
                tenant_id=ctx.tenant_id,
                name=name.strip(),
                version=version,
                case_refs=refs,
                created_by=ctx.subject_id,
            )
            session.add(row)
            session.commit()
            return _suite_view(row)

    # Execution ------------------------------------------------------------

    def start_run(self, ctx: TenantContext, suite_id: str) -> str:
        with self._session_factory() as session:
            suite = TenantScopedRepository(session, ctx.tenant_id).get(FunctionalTestSuite, suite_id)
            if suite is None:
                raise NotFoundError("Test suite not found")
            run = TestRun(
                id=new_ulid(),
                tenant_id=ctx.tenant_id,
                suite_id=suite.id,
                suite_version=suite.version,
                status="running",
                browser_version=self._sandbox.browser_version,
                started_at=utcnow_naive(),
                created_by=ctx.subject_id,
            )
            session.add(run)
            session.commit()
            run_id = run.id
            case_refs = list(suite.case_refs or [])

        outcomes: list[_StepOutcome] = []
        case_rows: list[FunctionalTestCase] = []
        with self._session_factory() as session:
            for ref in case_refs:
                case = TenantScopedRepository(session, ctx.tenant_id).get(
                    FunctionalTestCase, str(ref.get("case_id", ""))
                )
                if case is None or case.version != int(ref.get("version", 0)):
                    continue
                case_rows.append(case)

        for case in case_rows:
            steps = sorted((step_from_dict(item) for item in (case.steps or [])), key=lambda step: step.index)
            for step in steps:
                outcomes.append(self._run_step(ctx, case.id, step))

        status = "succeeded" if all(outcome.status in {"passed", "skipped"} for outcome in outcomes) else "failed"
        if not outcomes:
            status = "succeeded"
        self._persist_run(ctx, run_id, outcomes, status)
        self._persist_dead_letters(ctx, run_id, outcomes)
        return run_id

    def get_run(self, ctx: TenantContext, run_id: str) -> TestRunView:
        with self._session_factory() as session:
            run = TenantScopedRepository(session, ctx.tenant_id).get(TestRun, run_id)
            if run is None:
                raise NotFoundError("Test run not found")
            steps = list(
                session.scalars(
                    select(TestStep)
                    .where(TestStep.tenant_id == ctx.tenant_id, TestStep.run_id == run_id)
                    .order_by(TestStep.step_index, TestStep.id)
                )
            )
            return TestRunView(
                run_id=run.id,
                suite_id=run.suite_id,
                suite_version=str(run.suite_version),
                status=run.status,  # type: ignore[arg-type]
                steps=[
                    TestStepResult(
                        step_id=step.id,
                        status=step.status,  # type: ignore[arg-type]
                        duration_ms=step.duration_ms,
                        assertion=step.assertion,
                        evidence_ref=step.evidence_ref,
                        evidence_refs=dict(step.evidence_refs or {}),
                        attempts=step.attempts,
                    )
                    for step in steps
                ],
            )

    def dead_letters(self, ctx: TenantContext) -> list[dict[str, Any]]:
        with self._session_factory() as session:
            rows = list(
                session.scalars(
                    select(FunctionalDeadLetter)
                    .where(FunctionalDeadLetter.tenant_id == ctx.tenant_id)
                    .order_by(FunctionalDeadLetter.created_at, FunctionalDeadLetter.id)
                )
            )
        return [_dead_letter_view(row) for row in rows]

    def replay_dead_letter(self, ctx: TenantContext, letter_id: str) -> str:
        """Re-run the failed step's case and return the new run id."""

        with self._session_factory() as session:
            letter = TenantScopedRepository(session, ctx.tenant_id).get(FunctionalDeadLetter, letter_id)
            if letter is None:
                raise NotFoundError("Dead letter not found")
            if letter.replayed:
                raise InvalidArgumentError("dead letter is already replayed")
            run = TenantScopedRepository(session, ctx.tenant_id).get(TestRun, letter.run_id)
            if run is None:
                raise NotFoundError("Test run not found")
            case = TenantScopedRepository(session, ctx.tenant_id).get(FunctionalTestCase, letter.case_id)
            if case is None:
                raise NotFoundError("Test case not found")
            new_run = TestRun(
                id=new_ulid(),
                tenant_id=ctx.tenant_id,
                suite_id=run.suite_id,
                suite_version=run.suite_version,
                status="running",
                browser_version=self._sandbox.browser_version,
                started_at=utcnow_naive(),
                created_by=ctx.subject_id,
            )
            session.add(new_run)
            letter.replayed = True
            session.commit()
            run_id = new_run.id
            case_id = case.id
            steps = tuple(step_from_dict(item) for item in (case.steps or []))

        outcomes = [self._run_step(ctx, case_id, step) for step in sorted(steps, key=lambda item: item.index)]
        status = "succeeded" if all(outcome.status in {"passed", "skipped"} for outcome in outcomes) else "failed"
        if not outcomes:
            status = "succeeded"
        self._persist_run(ctx, run_id, outcomes, status)
        self._persist_dead_letters(ctx, run_id, outcomes)
        return run_id

    def record_visual_diff(
        self,
        ctx: TenantContext,
        *,
        run_id: str | None,
        step_id: str | None,
        expected_ref: str,
        actual_ref: str,
        threshold: float = 0.01,
        expected: ImageData,
        actual: ImageData,
        diff_ref: str | None = None,
    ) -> str:
        result = compare_images(expected, actual, threshold=threshold)
        with self._session_factory() as session:
            row = VisualDiff(
                id=new_ulid(),
                tenant_id=ctx.tenant_id,
                run_id=run_id,
                step_id=step_id,
                expected_ref=expected_ref,
                actual_ref=actual_ref,
                diff_ref=diff_ref,
                threshold=threshold,
                mismatch_ratio=result.mismatch_ratio,
                passed=result.passed,
            )
            session.add(row)
            session.commit()
            return row.id

    # Step execution -------------------------------------------------------

    def _run_step(self, ctx: TenantContext, case_id: str, step: StepSpec) -> _StepOutcome:
        step_id = new_ulid()
        if step.kind == "api":
            outcome = self._run_api_step(ctx, step)
        elif step.kind == "browser":
            outcome = self._run_browser_step(ctx, step)
        else:
            outcome = _StepOutcome(
                step_id=step_id,
                status="error",
                duration_ms=0,
                error=f"unsupported step kind: {step.kind}",
            )
        outcome.step_id = step_id
        outcome.case_id = case_id
        outcome.name = step.name
        outcome.kind = step.kind
        outcome.step_index = step.index
        return outcome

    def _run_api_step(self, ctx: TenantContext, step: StepSpec) -> _StepOutcome:
        request_data = step.request
        request = HttpRequestSpec(
            method=str(request_data.get("method", "GET")).upper(),
            url=str(request_data.get("url", "")),
            headers={str(key): str(value) for key, value in (request_data.get("headers") or {}).items()},
            json=request_data.get("json"),
            timeout_seconds=float(request_data.get("timeout_seconds", step.timeout_seconds)),
        )
        if not request.url:
            return _StepOutcome(
                step_id="",
                status="error",
                duration_ms=0,
                error="api step requires a url",
            )
        try:
            response = self._http.execute(request)
        except Exception as exc:  # noqa: BLE001 - retained as evidence
            ref = self._put(ctx, "error", {"step": step.name, "error": str(exc)})
            return _StepOutcome(
                step_id="",
                status="error",
                duration_ms=0,
                evidence_ref=ref,
                evidence_refs={"error": ref} if ref else {},
                error=str(exc),
            )
        outcomes = evaluate_assertions(step.assertions, response)
        response_ref = self._put(
            ctx,
            "http_response",
            {
                "status_code": response.status_code,
                "body": _safe_json(response.body),
                "duration_ms": response.duration_ms,
            },
        )
        status = "passed" if all(item.passed for item in outcomes) else "failed"
        return _StepOutcome(
            step_id="",
            status=status,
            duration_ms=response.duration_ms,
            assertion=summarize(outcomes),
            evidence_ref=response_ref,
            evidence_refs={"http_response": response_ref} if response_ref else {},
            outcomes=outcomes,
        )

    def _run_browser_step(self, ctx: TenantContext, step: StepSpec) -> _StepOutcome:
        url = str(step.request.get("url", ""))
        allow_hosts = step.allow_hosts or self._sandbox.network_allowlist
        if url:
            try:
                ensure_host_allowed(url, allow_hosts)
            except NetworkPolicyError as exc:
                ref = self._put(ctx, "network_policy", {"url": url, "error": str(exc)})
                return _StepOutcome(
                    step_id="",
                    status="error",
                    duration_ms=0,
                    evidence_ref=ref,
                    evidence_refs={"network_policy": ref} if ref else {},
                    error=str(exc),
                )
        result: BrowserResult | None = None
        attempts = 0
        while attempts < 2:
            attempts += 1
            try:
                result = self._browser.run(
                    step=step,
                    allow_hosts=allow_hosts,
                    timeout_seconds=min(step.timeout_seconds, self._sandbox.timeout_seconds),
                )
                break
            except BrowserTimeoutError as exc:
                if attempts >= 2:
                    return self._browser_failure(
                        ctx,
                        step,
                        exc,
                        status="failed",
                        duration_ms=int(step.timeout_seconds * 1000),
                        attempts=attempts,
                    )
            except Exception as exc:  # noqa: BLE001 - transient adapter failures
                if attempts >= 2:
                    return self._browser_failure(
                        ctx,
                        step,
                        exc,
                        status="error",
                        duration_ms=0,
                        attempts=attempts,
                    )

        if result is None:  # pragma: no cover - defensive; the loop always returns or sets a result
            return _StepOutcome(step_id="", status="error", duration_ms=0, error="browser returned no result")

        evidence_refs = self._collect_browser_evidence(ctx, result)
        outcomes = evaluate_assertions(step.assertions, result)
        if result.error:
            status = "error"
        elif outcomes and not all(item.passed for item in outcomes):
            status = "failed"
        else:
            status = "passed"
        return _StepOutcome(
            step_id="",
            status=status,
            duration_ms=result.duration_ms,
            assertion=summarize(outcomes),
            evidence_ref=_first_ref(evidence_refs),
            evidence_refs=evidence_refs,
            error=result.error,
            outcomes=outcomes,
            attempts=attempts,
        )

    def _browser_failure(
        self,
        ctx: TenantContext,
        step: StepSpec,
        exc: Exception,
        *,
        status: str,
        duration_ms: int,
        attempts: int,
    ) -> _StepOutcome:
        ref = self._put(ctx, "error", {"step": step.name, "error": str(exc)})
        return _StepOutcome(
            step_id="",
            status=status,
            duration_ms=duration_ms,
            evidence_ref=ref,
            evidence_refs={"error": ref} if ref else {},
            error=str(exc),
            attempts=attempts,
            dead_letter_reason=str(exc),
        )

    def _collect_browser_evidence(self, ctx: TenantContext, result: BrowserResult) -> dict[str, str]:
        refs: dict[str, str] = {}
        if result.screenshot is not None:
            ref = self._put(ctx, "screenshot", result.screenshot)
            if ref:
                refs["screenshot"] = ref
        if result.console:
            ref = self._put(ctx, "console", {"entries": list(result.console)})
            if ref:
                refs["console"] = ref
        if result.network:
            ref = self._put(ctx, "network", {"entries": list(result.network)})
            if ref:
                refs["network"] = ref
        if result.video is not None:
            ref = self._put(ctx, "video", result.video)
            if ref:
                refs["video"] = ref
        if result.trace is not None:
            ref = self._put(ctx, "trace", sanitize_evidence(result.trace))
            if ref:
                refs["trace"] = ref
        for kind, ref in result.evidence_refs.items():
            refs.setdefault(kind, ref)
        return refs

    def _put(self, ctx: TenantContext, kind: str, content: Any) -> str | None:
        try:
            return self._evidence.put(tenant_id=ctx.tenant_id, kind=kind, content=content)
        except Exception:  # noqa: BLE001 - evidence must not break the run
            return None

    def _persist_dead_letters(
        self,
        ctx: TenantContext,
        run_id: str,
        outcomes: list[_StepOutcome],
    ) -> None:
        with self._session_factory() as session:
            for outcome in outcomes:
                if outcome.dead_letter_reason is None:
                    continue
                exists = session.scalar(
                    select(FunctionalDeadLetter).where(
                        FunctionalDeadLetter.tenant_id == ctx.tenant_id,
                        FunctionalDeadLetter.run_id == run_id,
                        FunctionalDeadLetter.step_id == outcome.step_id,
                    )
                )
                if exists is not None:
                    continue
                session.add(
                    FunctionalDeadLetter(
                        id=new_ulid(),
                        tenant_id=ctx.tenant_id,
                        run_id=run_id,
                        step_id=outcome.step_id,
                        case_id=outcome.case_id,
                        reason=(outcome.dead_letter_reason or "step failed")[:1024],
                        payload={
                            "name": outcome.name,
                            "kind": outcome.kind,
                            "step_index": outcome.step_index,
                            "attempts": outcome.attempts,
                            "error": outcome.error,
                        },
                        attempts=outcome.attempts,
                        replayed=False,
                    )
                )
            session.commit()

    def _persist_run(
        self,
        ctx: TenantContext,
        run_id: str,
        outcomes: list[_StepOutcome],
        status: str,
    ) -> None:
        with self._session_factory() as session:
            run = TenantScopedRepository(session, ctx.tenant_id).get(TestRun, run_id)
            if run is None:
                return
            for index, outcome in enumerate(outcomes):
                session.add(
                    TestStep(
                        id=outcome.step_id,
                        tenant_id=ctx.tenant_id,
                        run_id=run_id,
                        case_id=outcome.case_id,
                        step_index=outcome.step_index if outcome.step_index else index,
                        name=outcome.name or f"step-{index}",
                        kind=outcome.kind or "api",
                        status=outcome.status,
                        attempts=outcome.attempts,
                        duration_ms=outcome.duration_ms,
                        assertion=outcome.assertion,
                        evidence_ref=outcome.evidence_ref,
                        evidence_refs=outcome.evidence_refs,
                        error=outcome.error,
                    )
                )
                for item in outcome.outcomes:
                    session.add(
                        AssertionRecord(
                            id=new_ulid(),
                            tenant_id=ctx.tenant_id,
                            step_id=outcome.step_id,
                            kind=item.kind,
                            config=_safe_json(item.config),
                            passed=item.passed,
                            expected={"value": _safe_json(item.expected)},
                            actual={"value": _safe_json(item.actual)},
                            message=(item.message or "")[:500],
                        )
                    )
            run.status = status
            run.finished_at = utcnow_naive()
            session.commit()


def _first_ref(refs: dict[str, str]) -> str | None:
    return next(iter(refs.values()), None)


def _dead_letter_view(row: FunctionalDeadLetter) -> dict[str, Any]:
    return {
        "id": row.id,
        "run_id": row.run_id,
        "step_id": row.step_id,
        "case_id": row.case_id,
        "reason": row.reason,
        "payload": row.payload or {},
        "attempts": row.attempts,
        "replayed": row.replayed,
        "created_at": row.created_at,
    }


def _case_view(row: FunctionalTestCase) -> TestCaseView:
    return TestCaseView(
        id=row.id,
        tenant_id=row.tenant_id,
        name=row.name,
        version=row.version,
        description=row.description,
        steps=tuple(step_from_dict(item) for item in (row.steps or [])),
    )


def _suite_view(row: FunctionalTestSuite) -> TestSuiteView:
    return TestSuiteView(
        id=row.id,
        tenant_id=row.tenant_id,
        name=row.name,
        version=row.version,
        case_refs=tuple(row.case_refs or ()),
    )


__all__ = ["FunctionalTestService", "step_from_dict"]
