"""Dataset resource: full schema for one dataset version."""

from __future__ import annotations

import json
from typing import Any

from mcp import types

from app.core.context import Principal
from app.core.errors import ForbiddenError, NotFoundError
from app.mcp.format import as_of
from app.services import ServiceRegistry

DATASET_SCOPE = "mcp:datasets:read"
_PREFIX = "pingce://datasets/"


def parse_uri(uri: str) -> tuple[str, int] | None:
    if not uri.startswith(_PREFIX):
        return None
    parts = uri[len(_PREFIX) :].split("/")
    if len(parts) != 4 or parts[1] != "versions" or parts[3] != "schema":
        return None
    try:
        version = int(parts[2])
    except ValueError:
        return None
    return parts[0], version


def read_dataset_schema(
    uri: str,
    *,
    services: ServiceRegistry,
    principal: Principal,
) -> types.ReadResourceResult | None:
    parsed = parse_uri(uri)
    if parsed is None:
        return None
    if not principal.has_scope(DATASET_SCOPE):
        raise ForbiddenError("Insufficient scope", required_scope=DATASET_SCOPE)
    dataset_id, version = parsed
    record = services.datasets.get_schema(principal.tenant_id, dataset_id, version)
    if record is None:
        raise NotFoundError("Dataset version not found", dataset_id=dataset_id)
    payload: dict[str, Any] = {
        "dataset_id": record.dataset_id,
        "version": record.version,
        "content_hash": record.content_hash,
        "row_count": record.row_count,
        "as_of": as_of(),
        "fields": [
            {
                "name": field.name,
                "type": field.type,
                "nullable": field.nullable,
                "description": field.description,
            }
            for field in record.fields
        ],
    }
    return types.ReadResourceResult(
        contents=[
            types.TextResourceContents(
                uri=uri,
                mime_type="application/json",
                text=json.dumps(payload, ensure_ascii=False, default=str),
            )
        ]
    )
