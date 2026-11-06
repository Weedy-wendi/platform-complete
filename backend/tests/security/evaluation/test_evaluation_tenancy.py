"""Cross-tenant run access is always NotFound (010 invariant 6)."""

from __future__ import annotations

import pytest

from app.core.errors import NotFoundError, TenantRequiredError
from app.modules.evaluation.service import EvaluationService
from tests.integration.evaluation.support import FakeAdapter, sample, start_request


def test_other_tenant_cannot_read_run_or_items(service: EvaluationService, ctx, other_ctx) -> None:
    run = service.start_run(ctx, start_request((sample("s1", "yes"),)))
    service.execute(ctx, run.run_id, adapter=FakeAdapter({"s1": "yes"}))

    with pytest.raises(NotFoundError):
        service.get_run(other_ctx, run.run_id)
    with pytest.raises(NotFoundError):
        service.list_items(other_ctx, run.run_id)
    with pytest.raises(NotFoundError):
        service.cancel(other_ctx, run.run_id)
    with pytest.raises(NotFoundError):
        service.execute(other_ctx, run.run_id, adapter=FakeAdapter({"s1": "yes"}))


def test_other_tenant_cannot_compare_or_list(service: EvaluationService, ctx, other_ctx) -> None:
    first = service.start_run(ctx, start_request((sample("s1", "yes"),), client_request_id="a"))
    second = service.start_run(ctx, start_request((sample("s1", "yes"),), client_request_id="b"))
    service.execute(ctx, first.run_id, adapter=FakeAdapter({"s1": "yes"}))
    service.execute(ctx, second.run_id, adapter=FakeAdapter({"s1": "yes"}))

    with pytest.raises(NotFoundError):
        service.compare(other_ctx, first.run_id, second.run_id)
    assert service.list_runs(other_ctx).items == []


def test_client_request_id_is_scoped_per_tenant(service: EvaluationService, ctx, other_ctx) -> None:
    request = start_request((sample("s1", "yes"),), client_request_id="shared")
    mine = service.start_run(ctx, request)
    theirs = service.start_run(other_ctx, request)
    assert mine.run_id != theirs.run_id
    assert service.get_run(ctx, mine.run_id).tenant_id == "tenant-a"
    assert service.get_run(other_ctx, theirs.run_id).tenant_id == "tenant-b"


def test_adapter_receives_only_tenant_context_not_repository(service: EvaluationService, ctx) -> None:
    class InspectingAdapter(FakeAdapter):
        def invoke(self, tenant_ctx, request):
            assert not hasattr(tenant_ctx, "session")
            assert set(request.__dataclass_fields__) <= {
                "sample_key",
                "payload",
                "expected",
                "trace_id",
                "raw_ref",
                "model",
                "temperature",
                "seed",
                "timeout_seconds",
            }
            return super().invoke(tenant_ctx, request)

    run = service.start_run(ctx, start_request((sample("s1", "yes"),)))
    assert service.execute(ctx, run.run_id, adapter=InspectingAdapter({"s1": "yes"})).status == "succeeded"


def test_invalid_tenant_context_is_rejected() -> None:
    from app.core.context import TenantContext

    with pytest.raises(TenantRequiredError):
        TenantContext(tenant_id="", subject_id="user:a")
