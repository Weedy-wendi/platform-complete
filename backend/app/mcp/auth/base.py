"""Authentication provider SPI."""

from __future__ import annotations

from typing import Protocol

from app.core.context import Principal


class AuthError(Exception):
    def __init__(
        self,
        message: str = "Unauthorized",
        *,
        status_code: int = 401,
        code: str = "UNAUTHORIZED",
        reason: str = "invalid",
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.code = code
        self.reason = reason


class AuthProvider(Protocol):
    async def authenticate(self, authorization: str | None) -> Principal: ...
