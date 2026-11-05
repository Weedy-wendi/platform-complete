"""API key authentication for MCP HTTP requests."""

from __future__ import annotations

import asyncio

from app.core.context import Principal
from app.core.errors import UnauthorizedError
from app.mcp.auth.base import AuthError
from app.modules.identity.public import ApiKeyService


class ApiKeyAuthProvider:
    def __init__(self, service: ApiKeyService) -> None:
        self._service = service

    async def authenticate(self, authorization: str | None) -> Principal:
        if not authorization:
            raise AuthError("Missing Authorization header", reason="missing")
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not token.strip():
            raise AuthError("Malformed Authorization header", reason="malformed")
        try:
            return await asyncio.to_thread(self._service.verify, token.strip())
        except UnauthorizedError as exc:
            raise AuthError(exc.message, reason=exc.code.lower()) from exc
