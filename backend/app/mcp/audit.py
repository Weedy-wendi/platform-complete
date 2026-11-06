"""Audit service used by MCP tool calls."""

from __future__ import annotations

from app.core.context import Principal
from app.core.logging import get_logger
from app.core.metrics import MCP_AUDIT_WRITE_FAILED
from app.modules.audit.public import AuditEvent, AuditWriter

logger = get_logger(__name__)


class McpAuditService:
    def __init__(self, writer: AuditWriter) -> None:
        self._writer = writer

    def record(
        self,
        *,
        principal: Principal,
        tool_name: str,
        tool_version: str,
        status: str,
        latency_ms: int,
        result_bytes: int,
        trace_id: str,
        error_code: str | None = None,
    ) -> None:
        event = AuditEvent(
            tenant_id=principal.tenant_id,
            api_key_id=principal.api_key_id or 0,
            client_name=principal.client_id,
            tool_name=tool_name,
            tool_version=tool_version,
            status=status,
            error_code=error_code,
            latency_ms=latency_ms,
            result_bytes=result_bytes,
            trace_id=trace_id,
        )
        try:
            self._writer.write(event)
        except Exception:
            MCP_AUDIT_WRITE_FAILED.inc()
            logger.exception("audit_write_failed", extra={"tool": tool_name, "trace_id": trace_id})
