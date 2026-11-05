"""MCP authentication package."""

from app.mcp.auth.base import AuthError, AuthProvider
from app.mcp.auth.factory import build_auth_provider

__all__ = ["AuthError", "AuthProvider", "build_auth_provider"]
