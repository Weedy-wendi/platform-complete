"""Liveness and readiness endpoints (not part of the business API)."""

from __future__ import annotations

from fastapi import APIRouter, Request
from starlette.responses import JSONResponse

from app.api.errors import trace_id_for
from app.core.health import readiness as readiness_check

router = APIRouter(tags=["health"])


@router.get("/healthz", openapi_extra={"security": []})
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/readyz", response_model=None, openapi_extra={"security": []})
def readyz(request: Request) -> JSONResponse:
    checks = getattr(request.app.state, "ready_checks", {}) or {}
    status, payload = readiness_check(checks)
    if status == 200:
        return JSONResponse(payload)
    trace_id = trace_id_for(request)
    return JSONResponse(
        {
            "code": "SERVICE_UNAVAILABLE",
            "message": "Dependency unavailable",
            "trace_id": trace_id,
            "details": payload,
        },
        status_code=503,
        headers={"X-Trace-Id": trace_id},
    )


__all__ = ["router"]
