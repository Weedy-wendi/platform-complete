"""Prometheus metrics endpoint."""

from __future__ import annotations

from fastapi import APIRouter
from starlette.responses import Response

from app.core.metrics import metrics_payload

router = APIRouter(tags=["health"])


@router.get("/metrics", include_in_schema=False, openapi_extra={"security": []})
def metrics() -> Response:
    payload, content_type = metrics_payload()
    return Response(content=payload, media_type=content_type)


__all__ = ["router"]
