"""Public functional-test contract.

The runner executes in-process; browsers and HTTP calls are injected adapters,
so the API process never spawns a browser directly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from app.core.context import TenantContext

StepStatus = Literal["passed", "failed", "skipped", "error"]
RunStatus = Literal["queued", "running", "succeeded", "failed", "cancelled"]


@dataclass(frozen=True)
class AssertionSpec:
    kind: str
    config: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class StepSpec:
    name: str
    kind: str
    request: dict[str, Any] = field(default_factory=dict)
    assertions: tuple[AssertionSpec, ...] = ()
    allow_hosts: tuple[str, ...] = ()
    timeout_seconds: float = 30.0
    index: int = 0


@dataclass(frozen=True)
class TestCaseSpec:
    name: str
    steps: tuple[StepSpec, ...]
    description: str = ""


@dataclass(frozen=True)
class TestCaseView:
    id: str
    tenant_id: str
    name: str
    version: int
    description: str = ""
    steps: tuple[StepSpec, ...] = ()


@dataclass(frozen=True)
class TestSuiteView:
    id: str
    tenant_id: str
    name: str
    version: int
    case_refs: tuple[dict[str, Any], ...] = ()


@dataclass(frozen=True)
class HttpRequestSpec:
    method: str = "GET"
    url: str = ""
    headers: dict[str, str] = field(default_factory=dict)
    json: Any = None
    timeout_seconds: float = 30.0


@dataclass(frozen=True)
class HttpResponse:
    status_code: int
    body: Any = None
    duration_ms: int = 0
    headers: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class BrowserResult:
    status_code: int | None = None
    body: Any = None
    duration_ms: int = 0
    screenshot: bytes | None = None
    console: tuple[dict[str, Any], ...] = ()
    network: tuple[dict[str, Any], ...] = ()
    evidence_refs: dict[str, str] = field(default_factory=dict)
    error: str | None = None
    video: bytes | None = None
    trace: dict[str, Any] | None = None


@dataclass(frozen=True)
class TestStepResult:
    step_id: str
    status: StepStatus
    duration_ms: int
    assertion: str | None = None
    evidence_ref: str | None = None
    evidence_refs: dict[str, str] = field(default_factory=dict)
    attempts: int = 1


@dataclass(frozen=True)
class TestRunView:
    run_id: str
    suite_id: str
    suite_version: str
    status: RunStatus
    steps: list[TestStepResult] = field(default_factory=list)


class BrowserTimeoutError(RuntimeError):
    """Raised by a browser adapter when the sandbox deadline is hit."""


class BrowserCrashError(RuntimeError):
    """Raised by a browser adapter after an unrecoverable crash."""


class NetworkPolicyError(RuntimeError):
    """Raised when a browser step targets a host outside the allowlist."""


class BrowserAdapter(Protocol):
    def run(
        self,
        *,
        step: StepSpec,
        allow_hosts: tuple[str, ...],
        timeout_seconds: float,
    ) -> BrowserResult: ...


class HttpExecutor(Protocol):
    def execute(self, request: HttpRequestSpec) -> HttpResponse: ...


class EvidenceWriter(Protocol):
    """Persist bytes/json and return an artifact id."""

    def put(
        self,
        *,
        tenant_id: str,
        kind: str,
        content: bytes | str | dict[str, Any],
        filename: str | None = None,
    ) -> str: ...


class FunctionalTestService(Protocol):
    def start_run(self, ctx: TenantContext, suite_id: str) -> str: ...

    def get_run(self, ctx: TenantContext, run_id: str) -> TestRunView: ...


__all__ = [
    "AssertionSpec",
    "BrowserAdapter",
    "BrowserCrashError",
    "BrowserResult",
    "BrowserTimeoutError",
    "EvidenceWriter",
    "FunctionalTestService",
    "HttpExecutor",
    "HttpRequestSpec",
    "HttpResponse",
    "NetworkPolicyError",
    "RunStatus",
    "StepSpec",
    "StepStatus",
    "TestCaseSpec",
    "TestCaseView",
    "TestRunView",
    "TestStepResult",
    "TestSuiteView",
]
