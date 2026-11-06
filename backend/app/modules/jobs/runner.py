"""Celery adapter and broker safety settings (JOB-02/03)."""

from __future__ import annotations

from typing import Any

from app.core.context import TenantContext
from app.modules.jobs.public_types import JobSpec

CELERY_CONFIG: dict[str, Any] = {
    "task_acks_late": True,
    "task_reject_on_worker_lost": True,
    "worker_prefetch_multiplier": 1,
    "broker_transport_options": {"visibility_timeout": 6 * 60 * 60},
    "task_default_queue": "pingce.jobs",
    "result_backend": None,
}


def build_celery_app(broker_url: str, *, backend_url: str | None = None) -> Any:
    from celery import Celery

    app = Celery("pingce", broker=broker_url, backend=backend_url)
    app.conf.update(CELERY_CONFIG)
    return app


class CeleryTaskRunner:
    """Thin adapter; business modules never import Celery directly."""

    def __init__(self, app: Any, *, task_name: str = "pingce.jobs.run") -> None:
        self._app = app
        self._task_name = task_name

    def enqueue(self, spec: JobSpec) -> str:
        result = self._app.send_task(
            self._task_name,
            kwargs={
                "job_type": spec.job_type,
                "payload": spec.payload,
                "idempotency_key": spec.idempotency_key,
            },
        )
        return str(result.id)

    def cancel(self, job_id: str, ctx: TenantContext) -> None:
        self._app.control.revoke(job_id, terminate=False)
        del ctx
