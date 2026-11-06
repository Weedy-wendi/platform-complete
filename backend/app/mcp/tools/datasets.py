"""Dataset tools: search, schema and sample preview."""

from __future__ import annotations

import asyncio
from typing import Any

from mcp import types

from app.core.errors import NotFoundError
from app.core.pagination import clamp_limit
from app.mcp.cursor import CursorCodec, query_fingerprint
from app.mcp.format import as_of, drop_none, isoformat_z, parse_datetime, success
from app.mcp.limits import fit_mapping, redact_mapping
from app.mcp.pagination import paginate
from app.mcp.registry import ToolCallContext, ToolRegistry
from app.services import ServiceRegistry

MAX_PAYLOAD_BYTES = 4096


def register(registry: ToolRegistry, services: ServiceRegistry, codec: CursorCodec) -> None:
    async def search_datasets(ctx: ToolCallContext, arguments: dict[str, Any]) -> types.CallToolResult:
        limit = clamp_limit(arguments.get("limit"), default=20, maximum=50)
        cursor = arguments.get("cursor")
        query_hash = query_fingerprint({k: v for k, v in arguments.items() if k != "cursor"})
        datasets = await asyncio.to_thread(
            services.datasets.search_datasets,
            ctx.principal.tenant_id,
            query=arguments.get("query"),
            project_id=arguments.get("project_id"),
            tags=tuple(arguments.get("tags") or ()),
            updated_after=parse_datetime(arguments.get("updated_after")),
        )
        page, next_cursor = paginate(
            datasets,
            limit=limit,
            cursor=cursor,
            codec=codec,
            tenant_id=ctx.principal.tenant_id,
            tool="search_datasets",
            query_hash=query_hash,
            key_fn=lambda dataset: (
                dataset.updated_at.isoformat() if dataset.updated_at else "",
                dataset.id,
            ),
        )
        payload: dict[str, Any] = {
            "items": [
                drop_none(
                    {
                        "id": dataset.id,
                        "name": dataset.name,
                        "project_id": dataset.project_id,
                        "latest_version": dataset.latest_version,
                        "sample_count": dataset.sample_count,
                        "tags": list(dataset.tags),
                        "updated_at": isoformat_z(dataset.updated_at),
                    }
                )
                for dataset in page
            ],
            "as_of": as_of(),
        }
        if next_cursor:
            payload["next_cursor"] = next_cursor
        return success(payload)

    async def get_dataset_schema(ctx: ToolCallContext, arguments: dict[str, Any]) -> types.CallToolResult:
        dataset_id = arguments["dataset_id"]
        version = arguments.get("version")
        record = await asyncio.to_thread(services.datasets.get_schema, ctx.principal.tenant_id, dataset_id, version)
        if record is None:
            raise NotFoundError("Dataset version not found", dataset_id=dataset_id)
        return success(
            {
                "dataset_id": record.dataset_id,
                "version": record.version,
                "content_hash": record.content_hash,
                "row_count": record.row_count,
                "fields": [
                    drop_none(
                        {
                            "name": schema_field.name,
                            "type": schema_field.type,
                            "nullable": schema_field.nullable,
                            "description": schema_field.description,
                        }
                    )
                    for schema_field in record.fields
                ],
                "as_of": as_of(),
            }
        )

    async def preview_samples(ctx: ToolCallContext, arguments: dict[str, Any]) -> types.CallToolResult:
        dataset_id = arguments["dataset_id"]
        version = arguments.get("version")
        limit = clamp_limit(arguments.get("limit"), default=5, maximum=20)
        cursor = arguments.get("cursor")
        query_hash = query_fingerprint({k: v for k, v in arguments.items() if k != "cursor"})

        schema = await asyncio.to_thread(services.datasets.get_schema, ctx.principal.tenant_id, dataset_id, version)
        if schema is None:
            raise NotFoundError("Dataset version not found", dataset_id=dataset_id)
        samples = await asyncio.to_thread(
            services.datasets.list_samples, ctx.principal.tenant_id, dataset_id, schema.version
        )
        page, next_cursor = paginate(
            samples,
            limit=limit,
            cursor=cursor,
            codec=codec,
            tenant_id=ctx.principal.tenant_id,
            tool="preview_samples",
            query_hash=query_hash,
            key_fn=lambda sample: (sample.id,),
        )

        items: list[dict[str, Any]] = []
        per_item_truncated = False
        for sample in page:
            payload_value, shrunk = fit_mapping(redact_mapping(sample.payload), max_bytes=MAX_PAYLOAD_BYTES)
            per_item_truncated = per_item_truncated or shrunk
            items.append(
                {
                    "sample_id": sample.id,
                    "payload": payload_value,
                    "tags": list(sample.tags),
                    "redacted": True,
                }
            )
        result: dict[str, Any] = {
            "items": items,
            "as_of": as_of(),
            "truncated": per_item_truncated,
        }
        if next_cursor:
            result["next_cursor"] = next_cursor
        return success(result)

    registry.register_handler("search_datasets", search_datasets)
    registry.register_handler("get_dataset_schema", get_dataset_schema)
    registry.register_handler("preview_samples", preview_samples)
