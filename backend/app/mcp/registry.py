"""MCP tool contract registry.

The registry is the single allowlist. Startup fails if the contract contains a
write tool, a missing annotation, or a name outside the approved set.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import jsonschema
import yaml
from jsonschema.exceptions import ValidationError
from mcp import types

from app.core.context import Principal
from app.core.errors import ForbiddenError, InvalidArgumentError, NotFoundError
from app.mcp.limits import cap_result, size_bytes

READ_ONLY_TOOL_NAMES: frozenset[str] = frozenset(
    {
        "list_projects",
        "search_datasets",
        "get_dataset_schema",
        "preview_samples",
        "list_evaluators",
        "get_run",
        "get_run_items",
        "compare_runs",
        "search_badcases",
        "check_gate",
    }
)

_WRITE_PREFIXES = ("create_", "update_", "delete_", "start_", "cancel_", "write_", "patch_", "remove_", "drop_")


@dataclass(frozen=True)
class ToolSpec:
    name: str
    title: str
    description: str
    scope: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    annotations: dict[str, Any]


@dataclass(frozen=True)
class ResourceSpec:
    name: str
    uri_template: str
    mime_type: str
    scope: str
    description: str


@dataclass(frozen=True)
class ToolCallContext:
    principal: Principal
    tool_name: str
    tool_version: str
    trace_id: str
    request_id: Any = None


ToolHandler = Callable[[ToolCallContext, dict[str, Any]], Awaitable[types.CallToolResult]]


class ToolRegistry:
    def __init__(
        self,
        *,
        tools: list[ToolSpec],
        resources: list[ResourceSpec],
        version: str,
        max_result_bytes: int,
    ) -> None:
        self._tools = {tool.name: tool for tool in tools}
        self._resources = {resource.name: resource for resource in resources}
        self._handlers: dict[str, ToolHandler] = {}
        self.version = version
        self.max_result_bytes = max_result_bytes
        self._validate_contract()

    @classmethod
    def from_contract(cls, path: Path, *, max_result_bytes: int = 65536) -> ToolRegistry:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        tools = [
            ToolSpec(
                name=item["name"],
                title=item.get("title", item["name"]),
                description=item.get("description", ""),
                scope=item["scope"],
                input_schema=item.get("inputSchema", {"type": "object"}),
                output_schema=item.get("outputSchema", {"type": "object"}),
                annotations=item.get("annotations", {}),
            )
            for item in raw.get("tools", [])
        ]
        resources = [
            ResourceSpec(
                name=item["name"],
                uri_template=item["uriTemplate"],
                mime_type=item.get("mimeType", "application/json"),
                scope=item.get("scope", ""),
                description=item.get("description", ""),
            )
            for item in raw.get("resources", [])
        ]
        return cls(
            tools=tools,
            resources=resources,
            version=str(raw.get("version", "1.0.0")),
            max_result_bytes=max_result_bytes,
        )

    def _validate_contract(self) -> None:
        names = set(self._tools)
        if names != READ_ONLY_TOOL_NAMES:
            missing = sorted(READ_ONLY_TOOL_NAMES - names)
            extra = sorted(names - READ_ONLY_TOOL_NAMES)
            raise ValueError(f"Tool contract mismatch; missing={missing}, extra={extra}")
        for tool in self._tools.values():
            if tool.name.startswith(_WRITE_PREFIXES):
                raise ValueError(f"Write tool is not allowed: {tool.name}")
            if tool.annotations.get("readOnlyHint") is not True:
                raise ValueError(f"Tool {tool.name} must set readOnlyHint=true")
            if tool.annotations.get("destructiveHint") is not False:
                raise ValueError(f"Tool {tool.name} must set destructiveHint=false")
            if tool.annotations.get("idempotentHint") is not True:
                raise ValueError(f"Tool {tool.name} must set idempotentHint=true")
            if tool.annotations.get("openWorldHint") is not False:
                raise ValueError(f"Tool {tool.name} must set openWorldHint=false")
            if not tool.scope:
                raise ValueError(f"Tool {tool.name} must declare a scope")

    @property
    def tool_names(self) -> frozenset[str]:
        return frozenset(self._tools)

    def register_handler(self, name: str, handler: ToolHandler) -> None:
        if name not in self._tools:
            raise ValueError(f"Cannot register handler for unknown tool: {name}")
        self._handlers[name] = handler

    def list_tools(self) -> list[types.Tool]:
        result: list[types.Tool] = []
        for spec in self._tools.values():
            annotations = types.ToolAnnotations(
                title=spec.annotations.get("title"),
                read_only_hint=spec.annotations.get("readOnlyHint"),
                destructive_hint=spec.annotations.get("destructiveHint"),
                idempotent_hint=spec.annotations.get("idempotentHint"),
                open_world_hint=spec.annotations.get("openWorldHint"),
            )
            result.append(
                types.Tool(
                    name=spec.name,
                    title=spec.title,
                    description=spec.description,
                    input_schema=spec.input_schema,
                    output_schema=spec.output_schema,
                    annotations=annotations,
                )
            )
        return result

    def list_resource_templates(self) -> list[types.ResourceTemplate]:
        return [
            types.ResourceTemplate(
                name=resource.name,
                uri_template=resource.uri_template,
                description=resource.description,
                mime_type=resource.mime_type,
            )
            for resource in self._resources.values()
        ]

    def get(self, name: str) -> ToolSpec:
        spec = self._tools.get(name)
        if spec is None:
            raise NotFoundError("Tool not found", tool=name)
        return spec

    async def call_tool(self, name: str, arguments: dict[str, Any], ctx: ToolCallContext) -> types.CallToolResult:
        spec = self.get(name)
        if not ctx.principal.has_scope(spec.scope):
            raise ForbiddenError("Insufficient scope", required_scope=spec.scope)

        try:
            jsonschema.validate(instance=arguments, schema=spec.input_schema)
        except ValidationError as exc:
            raise InvalidArgumentError(exc.message, path=list(exc.absolute_path)) from exc

        handler = self._handlers.get(name)
        if handler is None:
            return types.CallToolResult(
                is_error=True,
                content=[types.TextContent(text="Tool is not implemented yet")],
                structured_content={
                    "code": "NOT_IMPLEMENTED",
                    "message": f"{name} is not implemented yet",
                    "retryable": False,
                },
            )

        result = await handler(ctx, arguments)
        payload = result.model_dump(mode="json")
        if size_bytes(payload) > self.max_result_bytes:
            if result.structured_content is not None:
                capped, truncated = cap_result(result.structured_content, max_bytes=self.max_result_bytes)
                if truncated:
                    return types.CallToolResult(
                        content=[types.TextContent(text="Result truncated")],
                        structured_content=capped,
                        is_error=False,
                    )
            return types.CallToolResult(
                is_error=True,
                content=[types.TextContent(text="Result exceeds the 64KB limit")],
                structured_content={
                    "code": "RESULT_TOO_LARGE",
                    "message": "Result exceeds the 64KB limit",
                    "retryable": False,
                },
            )
        return result

    async def call_tool_with_timeout(
        self,
        name: str,
        arguments: dict[str, Any],
        ctx: ToolCallContext,
        timeout_seconds: float,
    ) -> types.CallToolResult:
        """Execute a tool with a hard timeout (Constitution MCP §4)."""
        try:
            return await asyncio.wait_for(
                self.call_tool(name, arguments, ctx),
                timeout=max(0.001, timeout_seconds),
            )
        except TimeoutError:
            return types.CallToolResult(
                is_error=True,
                content=[types.TextContent(text="Tool execution timed out")],
                structured_content={
                    "code": "TOOL_TIMEOUT",
                    "message": f"Tool execution exceeded {timeout_seconds:g}s",
                    "retryable": True,
                },
            )
