"""Authentication adapters.

The identity module owns bearer parsing and the API-key verifier contract, but
not the HTTP framework. ``build_fastapi_dependency`` is the thin adapter the
REST layer will use once ``017-rest-api`` lands.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from app.core.context import Principal
from app.core.errors import UnauthorizedError
from app.modules.identity.policies import require_any_scope, require_scope
from app.modules.identity.tenant_status import SqlTenantStatusChecker, TenantStatusChecker


class ApiKeyVerifier(Protocol):
    def verify(self, raw_key: str) -> Principal: ...


def extract_bearer_token(authorization: str | None) -> str:
    if not authorization:
        raise UnauthorizedError("Missing Authorization header")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise UnauthorizedError("Malformed Authorization header")
    return token.strip()


class ApiKeyAuthenticator:
    def __init__(
        self,
        verifier: ApiKeyVerifier,
        *,
        tenant_status_checker: TenantStatusChecker | None = None,
    ) -> None:
        self._verifier = verifier
        self._tenant_status_checker = tenant_status_checker

    def authenticate(self, authorization: str | None) -> Principal:
        principal = self._verifier.verify(extract_bearer_token(authorization))
        checker = self._tenant_status_checker
        if checker is not None and not checker.is_active(principal.tenant_id):
            raise UnauthorizedError("Tenant is disabled")
        return principal


class JwtAuthenticator:
    """Reserved adapter; JWT/OIDC is not enabled in P0.

    A verifier can be injected by the deployment once the JWT profile is
    enabled; without one the adapter rejects all tokens.
    """

    def __init__(self, verifier: Callable[[str], Principal] | None = None) -> None:
        self._verifier = verifier

    def authenticate(self, authorization: str | None) -> Principal:
        token = extract_bearer_token(authorization)
        if self._verifier is None:
            raise UnauthorizedError("JWT authentication is not enabled")
        return self._verifier(token)


def build_fastapi_dependency(authenticator: ApiKeyAuthenticator) -> Callable[..., Principal]:
    """Return a FastAPI dependency that resolves the bearer API key.

    FastAPI is imported lazily so the service layer stays framework-agnostic.
    """
    from fastapi import Header

    def dependency(authorization: str | None = Header(default=None)) -> Principal:
        return authenticator.authenticate(authorization)

    return dependency


__all__ = [
    "ApiKeyAuthenticator",
    "ApiKeyVerifier",
    "JwtAuthenticator",
    "SqlTenantStatusChecker",
    "TenantStatusChecker",
    "build_fastapi_dependency",
    "extract_bearer_token",
    "require_any_scope",
    "require_scope",
]
