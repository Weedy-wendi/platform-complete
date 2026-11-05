"""Shared evaluation test helpers."""

from __future__ import annotations

from app.core.context import TenantContext
from app.modules.evaluation.types import AgentRequest, AgentResponse, SampleInput, StartRunRequest

DATASET_HASH = "a" * 64
EVALUATOR = {
    "id": "ev-accuracy",
    "name": "exact",
    "kind": "rule",
    "rule": "exact_match",
    "metric": {"name": "accuracy", "direction": "higher_is_better"},
}
JUDGE_EVALUATOR = {
    "id": "ev-judge",
    "name": "quality",
    "kind": "judge",
    "rubric": "Is the answer correct and clear?",
    "metric": {"name": "quality", "direction": "higher_is_better"},
    "threshold": 0.6,
}
METRICS = [{"name": "accuracy", "direction": "higher_is_better"}]
JUDGE_METRICS = [{"name": "quality", "direction": "higher_is_better"}]
TARGET = {"adapter": "fake", "model": "fake-1", "temperature": 0.0, "seed": 7}


class FakeAdapter:
    def __init__(
        self,
        outputs: dict[str, str] | None = None,
        *,
        fail_on: set[str] | None = None,
        cost_usd: float = 0.01,
    ) -> None:
        self.outputs = outputs or {}
        self.fail_on = fail_on or set()
        self.cost_usd = cost_usd
        self.calls: list[str] = []

    def invoke(self, ctx: TenantContext, request: AgentRequest) -> AgentResponse:
        self.calls.append(request.sample_key)
        if request.sample_key in self.fail_on:
            raise TimeoutError(f"timeout for {request.sample_key}")
        output = self.outputs.get(request.sample_key, request.expected if request.expected is not None else "")
        return AgentResponse(
            output=str(output),
            trace_id=f"trace-{request.sample_key}",
            usage={"prompt_tokens": 1, "completion_tokens": 1},
            cost_usd=self.cost_usd,
            raw_ref=f"artifact://raw/{ctx.tenant_id}/{request.sample_key}.json",
        )


class RecordingAdapter(FakeAdapter):
    def __init__(self, store: dict[str, object], outputs: dict[str, str] | None = None, **kwargs: object) -> None:
        super().__init__(outputs, **kwargs)  # type: ignore[arg-type]
        self.store = store

    def invoke(self, ctx: TenantContext, request: AgentRequest) -> AgentResponse:
        response = super().invoke(ctx, request)
        key = f"raw/{ctx.tenant_id}/{request.sample_key}"
        self.store[key] = {"output": response.output, "usage": response.usage, "trace_id": response.trace_id}
        return AgentResponse(
            output=response.output,
            trace_id=response.trace_id,
            usage=response.usage,
            cost_usd=response.cost_usd,
            raw_ref=key,
        )


def sample(key: str, expected: str, **payload: object) -> SampleInput:
    return SampleInput(key, {"input": f"question {key}", **payload}, expected=expected)


def start_request(
    samples: tuple[SampleInput, ...],
    *,
    client_request_id: str = "req-1",
    evaluators: tuple[dict, ...] = (EVALUATOR,),
    metrics: tuple[dict, ...] = tuple(METRICS),
    target_config: dict | None = None,
    mode: str = "record",
    budget_usd: float | None = None,
    target_config_version: str = "cfg-1",
    adapter_version: str = "v1",
    suite_id: str | None = None,
    suite_version: int | None = None,
) -> StartRunRequest:
    return StartRunRequest(
        client_request_id=client_request_id,
        dataset_id="dataset-1",
        dataset_version=1,
        dataset_hash=DATASET_HASH,
        samples=samples,
        target_config=dict(target_config or TARGET),
        evaluator_versions=evaluators,
        metric_configs=metrics,
        sampling={"strategy": "full", "seed": 42},
        code_version="code-1",
        adapter_version=adapter_version,
        target_config_version=target_config_version,
        mode=mode,  # type: ignore[arg-type]
        env="test",
        suite_id=suite_id,
        suite_version=suite_version,
        budget_usd=budget_usd,
    )
