"""Run creation, execution, cancellation, budget and replay (EVL-05/06/07/16)."""

from __future__ import annotations

from dataclasses import replace

import pytest
from sqlalchemy import select

from app.core.errors import InvalidArgumentError
from app.modules.evaluation.judge import StaticJudgeGateway
from app.modules.evaluation.models import JudgeCall, Run
from app.modules.evaluation.service import EvaluationService
from app.modules.evaluation.types import SampleInput
from tests.integration.evaluation.support import (
    JUDGE_EVALUATOR,
    JUDGE_METRICS,
    FakeAdapter,
    RecordingAdapter,
    sample,
    start_request,
)


def test_run_creation_is_idempotent(service: EvaluationService, ctx) -> None:
    request = start_request((sample("s1", "yes"), sample("s2", "no")))
    first = service.start_run(ctx, request)
    second = service.start_run(ctx, request)
    assert first.run_id == second.run_id
    assert first.manifest_hash == second.manifest_hash
    assert first.total_items == 2
    assert first.status == "queued"

    other = service.start_run(ctx, replace(request, client_request_id="req-2"))
    assert other.run_id != first.run_id
    assert other.manifest_hash == first.manifest_hash


def test_executor_handles_partial_failure_and_progress(service: EvaluationService, ctx) -> None:
    request = start_request((sample("s1", "yes"), sample("s2", "yes"), sample("s3", "yes")))
    run = service.start_run(ctx, request)
    adapter = FakeAdapter({"s1": "yes", "s3": "yes"}, fail_on={"s2"})
    view = service.execute(ctx, run.run_id, adapter=adapter)

    assert view.status == "succeeded"
    assert view.succeeded_items == 2
    assert view.failed_items == 1
    assert view.progress == 100
    assert view.cost_usd == pytest.approx(0.02)
    assert adapter.calls == ["s1", "s2", "s3"]

    page = service.list_items(ctx, run.run_id)
    statuses = {item.sample_key: item.status for item in page.items}
    assert statuses == {"s1": "succeeded", "s2": "failed", "s3": "succeeded"}
    failed = next(item for item in page.items if item.sample_key == "s2")
    assert failed.error and "TimeoutError" in failed.error
    succeeded = next(item for item in page.items if item.sample_key == "s1")
    assert succeeded.scores[0].metric_name == "accuracy"
    assert succeeded.scores[0].value == 1.0


def test_cancel_keeps_completed_items(service: EvaluationService, ctx) -> None:
    request = start_request((sample("s1", "yes"), sample("s2", "yes")))
    run = service.start_run(ctx, request)
    cancelled = service.cancel(ctx, run.run_id)
    assert cancelled.status == "cancelled"
    assert cancelled.succeeded_items == 0

    adapter = FakeAdapter({"s1": "yes", "s2": "yes"})
    view = service.execute(ctx, run.run_id, adapter=adapter)
    assert view.status == "cancelled"
    assert adapter.calls == []
    assert all(item.status == "pending" for item in service.list_items(ctx, run.run_id).items)


def test_budget_pauses_and_resumes(service: EvaluationService, ctx, factory) -> None:
    request = start_request(
        (sample("s1", "yes"), sample("s2", "yes"), sample("s3", "yes")),
        budget_usd=0.5,
    )
    run = service.start_run(ctx, request)
    adapter = FakeAdapter({"s1": "yes", "s2": "yes", "s3": "yes"}, cost_usd=1.0)
    paused = service.execute(ctx, run.run_id, adapter=adapter)
    assert paused.status == "paused_budget"
    assert paused.error == "budget exceeded"
    assert paused.succeeded_items == 1
    assert adapter.calls == ["s1"]

    with factory() as session:
        row = session.get(Run, run.run_id)
        assert row is not None
        row.budget_usd = 10.0
        session.commit()

    resumed = service.execute(ctx, run.run_id, adapter=adapter)
    assert resumed.status == "succeeded"
    assert resumed.succeeded_items == 3
    assert resumed.failed_items == 0
    assert resumed.progress == 100


def test_budget_is_validated_at_creation(service: EvaluationService, ctx) -> None:
    request = start_request((sample("s1", "yes"),), budget_usd=1.0)
    with pytest.raises(InvalidArgumentError):
        service.start_run(ctx, replace(request, estimated_cost_usd=2.0))


def test_record_then_replay_never_calls_agent(service: EvaluationService, ctx) -> None:
    store: dict[str, object] = {}
    outputs = {"s1": "yes", "s2": "no"}
    record_samples = (sample("s1", "yes"), sample("s2", "yes"))
    record_run = service.start_run(ctx, start_request(record_samples, client_request_id="record-1"))
    record = service.execute(ctx, record_run.run_id, adapter=RecordingAdapter(store, outputs))
    assert record.status == "succeeded"
    record_items = service.list_items(ctx, record_run.run_id).items
    assert all(item.raw_ref for item in record_items)

    replay_samples = tuple(
        SampleInput(item.sample_key, {"input": f"question {item.sample_key}"}, expected="yes", raw_ref=item.raw_ref)
        for item in record_items
    )
    replay_request = start_request(replay_samples, client_request_id="replay-1", mode="replay")
    replay_run = service.start_run(ctx, replay_request)
    assert replay_run.mode == "replay"

    exploding = FakeAdapter(fail_on={"s1", "s2"})
    replay = service.execute(ctx, replay_run.run_id, adapter=exploding, artifact_store=store)
    assert replay.status == "succeeded"
    assert replay.mode == "replay"
    assert exploding.calls == []

    replay_items = service.list_items(ctx, replay_run.run_id).items
    assert {item.sample_key: item.output for item in replay_items} == {"s1": "yes", "s2": "no"}
    assert {item.sample_key: item.scores[0].value for item in replay_items} == {"s1": 1.0, "s2": 0.0}


def test_repeated_runs_are_reproducible(service: EvaluationService, ctx) -> None:
    hashes: set[str] = set()
    values: list[float] = []
    adapter = FakeAdapter({"s1": "yes", "s2": "yes"})
    for index in range(5):
        run = service.start_run(
            ctx,
            start_request(
                (sample("s1", "yes"), sample("s2", "yes")),
                client_request_id=f"repro-{index}",
            ),
        )
        executed = service.execute(ctx, run.run_id, adapter=adapter)
        assert executed.status == "succeeded"
        hashes.add(executed.manifest_hash)
        values.append(executed.metric("accuracy").value)  # type: ignore[union-attr]
    assert len(hashes) == 1
    assert values == [1.0] * 5


def test_judge_run_records_judge_call(factory, ctx) -> None:
    service = EvaluationService(
        factory,
        judge_gateway=StaticJudgeGateway('{"score": 0.8, "reasoning": "correct and clear"}'),
        max_workers=1,
    )
    request = start_request(
        (sample("s1", "yes"),),
        client_request_id="judge-1",
        evaluators=(JUDGE_EVALUATOR,),
        metrics=tuple(JUDGE_METRICS),
    )
    run = service.start_run(ctx, request)
    view = service.execute(ctx, run.run_id, adapter=FakeAdapter({"s1": "yes"}))
    assert view.status == "succeeded"
    assert view.metric("quality").value == pytest.approx(0.8)  # type: ignore[union-attr]

    with factory() as session:
        rows = list(session.scalars(select(JudgeCall).where(JudgeCall.run_id == run.run_id)))
    assert len(rows) == 1
    assert rows[0].status == "succeeded"
    assert rows[0].score == pytest.approx(0.8)
    assert rows[0].prompt_hash
    item = service.list_items(ctx, run.run_id).items[0]
    assert item.scores[0].metric_name == "quality"


def test_judge_invalid_output_records_failed_call(factory, ctx) -> None:
    service = EvaluationService(factory, judge_gateway=StaticJudgeGateway("not-json"), max_workers=1)
    request = start_request(
        (sample("s1", "yes"),),
        client_request_id="judge-bad",
        evaluators=(JUDGE_EVALUATOR,),
        metrics=tuple(JUDGE_METRICS),
    )
    run = service.start_run(ctx, request)
    view = service.execute(ctx, run.run_id, adapter=FakeAdapter({"s1": "yes"}))
    assert view.status == "failed"
    assert view.failed_items == 1
    with factory() as session:
        rows = list(session.scalars(select(JudgeCall).where(JudgeCall.run_id == run.run_id)))
    assert len(rows) == 1
    assert rows[0].status == "failed"
    assert rows[0].error and "judge output" in rows[0].error
