"""Canonical target DTOs live with the evaluation public types.

This module is a stable import location for adapter authors.
"""

from app.modules.evaluation.types import AgentRequest, AgentResponse, TargetAdapter, TraceSource, TraceSpan

__all__ = ["AgentRequest", "AgentResponse", "TargetAdapter", "TraceSource", "TraceSpan"]
