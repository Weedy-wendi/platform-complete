"""Auth provider factory."""

from __future__ import annotations

from app.core.config import Settings
from app.mcp.auth.api_key import ApiKeyAuthProvider
from app.mcp.auth.base import AuthProvider
from app.mcp.auth.oauth_stub import OAuthResourceServerProvider
from app.modules.identity.public import ApiKeyService


def build_auth_provider(settings: Settings, api_key_service: ApiKeyService) -> AuthProvider:
    if settings.mcp_auth_mode == "api_key":
        return ApiKeyAuthProvider(api_key_service)
    if settings.mcp_auth_mode == "oauth":
        return OAuthResourceServerProvider(
            issuer=settings.mcp_oauth_issuer or "",
            audience=settings.mcp_oauth_audience or "",
            jwks_url=settings.mcp_oauth_jwks_url or "",
        )
    raise ValueError(f"Unsupported MCP_AUTH_MODE: {settings.mcp_auth_mode}")
