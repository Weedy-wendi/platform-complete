import contextvars

import pytest

from app.core.context import (
    Principal,
    TenantContext,
    get_principal,
    get_tenant_context,
    reset_principal,
    reset_tenant_context,
    set_principal,
    set_tenant_context,
)
from app.core.errors import TenantRequiredError


def test_principal_required() -> None:
    with pytest.raises(TenantRequiredError):
        get_principal()


def test_tenant_context_required() -> None:
    def run() -> None:
        with pytest.raises(TenantRequiredError):
            get_tenant_context()

    contextvars.Context().run(run)


def test_set_and_reset_tenant_context() -> None:
    context = TenantContext(tenant_id="tenant-a", subject_id="user:1", trace_id="trace")
    token = set_tenant_context(context)
    try:
        assert get_tenant_context() == context
    finally:
        reset_tenant_context(token)
    with pytest.raises(TenantRequiredError):
        get_tenant_context()


def test_tenant_context_from_principal() -> None:
    principal = Principal(tenant_id="tenant-a", subject="user:1", scopes=frozenset({"projects:read"}))
    context = TenantContext.from_principal(principal, trace_id="trace-1")
    assert context.tenant_id == "tenant-a"
    assert context.subject_id == "user:1"
    assert context.scopes == frozenset({"projects:read"})
    assert context.trace_id == "trace-1"
    assert principal.subject_id == "user:1"
    assert principal.auth_method == "api_key"

    jwt_principal = Principal(
        tenant_id="tenant-a",
        subject="user:2",
        auth_method="jwt",
    )
    assert jwt_principal.auth_method == "jwt"


def test_empty_tenant_id_is_rejected() -> None:
    with pytest.raises(TenantRequiredError):
        TenantContext(tenant_id="", subject_id="user:1")


def test_set_and_reset_principal() -> None:
    principal = Principal(tenant_id="tenant-a", subject="user:1", scopes=frozenset({"mcp:projects:read"}))
    token = set_principal(principal)
    try:
        assert get_principal() == principal
    finally:
        reset_principal(token)
    with pytest.raises(TenantRequiredError):
        get_principal()
