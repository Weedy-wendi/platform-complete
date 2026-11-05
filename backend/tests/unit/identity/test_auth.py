"""Authentication adapter tests (IDN-04)."""

from __future__ import annotations

import pytest

from app.core.errors import ForbiddenError, UnauthorizedError
from app.modules.identity.api_key import ApiKeyService
from app.modules.identity.auth import (
    ApiKeyAuthenticator,
    JwtAuthenticator,
    extract_bearer_token,
    require_any_scope,
    require_scope,
)


def test_extract_bearer_token() -> None:
    assert extract_bearer_token("Bearer pk_test_abc_def") == "pk_test_abc_def"
    with pytest.raises(UnauthorizedError):
        extract_bearer_token(None)
    with pytest.raises(UnauthorizedError):
        extract_bearer_token("Basic abc")
    with pytest.raises(UnauthorizedError):
        extract_bearer_token("Bearer ")


def test_api_key_authenticator_returns_principal(api_key_service: ApiKeyService) -> None:
    issued = api_key_service.issue(tenant_id="tenant-a", name="ci", scopes={"mcp:projects:read"})
    authenticator = ApiKeyAuthenticator(api_key_service)
    principal = authenticator.authenticate(f"Bearer {issued.raw_key}")
    assert principal.tenant_id == "tenant-a"
    assert principal.auth_method == "api_key"
    assert principal.has_scope("mcp:projects:read")


def test_api_key_authenticator_rejects_invalid_keys(api_key_service: ApiKeyService) -> None:
    authenticator = ApiKeyAuthenticator(api_key_service)
    with pytest.raises(UnauthorizedError):
        authenticator.authenticate("Bearer not-a-key")


def test_scope_helpers_raise_403(api_key_service: ApiKeyService) -> None:
    issued = api_key_service.issue(tenant_id="tenant-a", name="ci", scopes={"mcp:projects:read"})
    principal = ApiKeyAuthenticator(api_key_service).authenticate(f"Bearer {issued.raw_key}")
    require_scope(principal, "mcp:projects:read")
    require_any_scope(principal, {"mcp:projects:read", "mcp:eval:read"})
    with pytest.raises(ForbiddenError):
        require_scope(principal, "mcp:eval:read")


def test_jwt_is_reserved_and_rejected() -> None:
    with pytest.raises(UnauthorizedError):
        JwtAuthenticator().authenticate("Bearer some.jwt.token")


def test_jwt_authenticator_returns_principal_when_configured() -> None:
    from app.core.context import Principal

    def verifier(token: str) -> Principal:
        assert token == "some.jwt.token"
        return Principal(tenant_id="tenant-a", subject="user:1", auth_method="jwt")

    principal = JwtAuthenticator(verifier).authenticate("Bearer some.jwt.token")
    assert principal.auth_method == "jwt"
    assert principal.tenant_id == "tenant-a"


def test_authenticator_rejects_inactive_tenant(api_key_service: ApiKeyService) -> None:
    class InactiveTenant:
        def is_active(self, tenant_id: str) -> bool:
            return False

    issued = api_key_service.issue(tenant_id="tenant-a", name="ci", scopes={"mcp:projects:read"})
    authenticator = ApiKeyAuthenticator(api_key_service, tenant_status_checker=InactiveTenant())
    with pytest.raises(UnauthorizedError):
        authenticator.authenticate(f"Bearer {issued.raw_key}")
