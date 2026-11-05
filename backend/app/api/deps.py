"""FastAPI dependencies for authentication, tenancy, scopes and services."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Header, Request

from app.api.ports import (
    AdminPort,
    DatasetsPort,
    DatasourcesPort,
    EvaluationPort,
    FunctionalPort,
    GatePort,
    ProjectsPort,
    ReportsPort,
    SearchPort,
    SuitesPort,
    TargetsPort,
)
from app.api.services import ApiServices
from app.core.context import (
    Principal,
    TenantContext,
    reset_principal,
    reset_tenant_context,
    set_principal,
    set_tenant_context,
)
from app.core.errors import ForbiddenError, UnauthorizedError
from app.modules.identity.public import ApiKeyAuthenticator

_WILDCARD_SCOPES = frozenset({"*", "platform:admin"})

# REST scopes are the contract; the mcp:* scopes are accepted as read aliases
# so existing read-only keys can call the REST read surface during migration.
_SCOPE_ALIASES: dict[str, frozenset[str]] = {
    "projects:read": frozenset({"projects:read", "projects:write", "mcp:projects:read"}),
    "projects:write": frozenset({"projects:write"}),
    "datasets:read": frozenset({"datasets:read", "datasets:write", "mcp:datasets:read"}),
    "datasets:write": frozenset({"datasets:write"}),
    "datasources:read": frozenset({"datasources:read", "datasources:write", "mcp:datasources:read"}),
    "datasources:write": frozenset({"datasources:write"}),
    "runs:read": frozenset({"runs:read", "runs:write", "evaluation:read", "mcp:eval:read"}),
    "runs:write": frozenset({"runs:write", "evaluation:write"}),
    "evaluators:read": frozenset({"evaluators:read", "evaluators:write", "evaluation:read", "mcp:eval:read"}),
    "evaluators:write": frozenset({"evaluators:write", "evaluation:write"}),
    "gate:read": frozenset({"gate:read", "gates:read", "mcp:gate:read"}),
    "reports:read": frozenset({"reports:read", "report:read", "mcp:eval:read"}),
    "badcases:read": frozenset({"badcases:read", "mcp:badcases:read"}),
    "functional:read": frozenset({"functional:read", "functional:write"}),
    "functional:write": frozenset({"functional:write"}),
    "admin:read": frozenset({"admin:read"}),
    "admin:write": frozenset({"admin:write"}),
}


class _DenyAllVerifier:
    def verify(self, raw_key: str) -> Principal:
        raise UnauthorizedError("Invalid API key")


def _deny_all_authenticator() -> ApiKeyAuthenticator:
    return ApiKeyAuthenticator(_DenyAllVerifier())


def get_authenticator(request: Request) -> ApiKeyAuthenticator:
    authenticator = getattr(request.app.state, "authenticator", None)
    return authenticator or _deny_all_authenticator()


def get_principal(
    request: Request,
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
) -> Principal:
    principal = get_authenticator(request).authenticate(authorization)
    # Keep the authenticated identity on the request so the write-audit
    # middleware can attribute denied (403) attempts after dependencies unwind.
    request.state.principal = principal
    return principal


async def get_tenant_context(
    request: Request,
    principal: Annotated[Principal, Depends(get_principal)],
) -> AsyncIterator[TenantContext]:
    trace_id = getattr(request.state, "trace_id", "")
    context = TenantContext.from_principal(principal, trace_id=trace_id)
    principal_token = set_principal(principal)
    context_token = set_tenant_context(context)
    try:
        yield context
    finally:
        reset_tenant_context(context_token)
        reset_principal(principal_token)


def get_services(request: Request) -> ApiServices:
    return request.app.state.api_services


def get_projects(request: Request) -> ProjectsPort:
    return get_services(request).projects


def get_datasets(request: Request) -> DatasetsPort:
    return get_services(request).datasets


def get_datasources(request: Request) -> DatasourcesPort:
    return get_services(request).datasources


def get_evaluation(request: Request) -> EvaluationPort:
    return get_services(request).evaluation


def get_suites(request: Request) -> SuitesPort:
    return get_services(request).suites


def get_targets(request: Request) -> TargetsPort:
    return get_services(request).targets


def get_gates(request: Request) -> GatePort:
    return get_services(request).gates


def get_reports(request: Request) -> ReportsPort:
    return get_services(request).reports


def get_search(request: Request) -> SearchPort:
    return get_services(request).search


def get_admin(request: Request) -> AdminPort:
    return get_services(request).admin


def get_functional(request: Request) -> FunctionalPort:
    return get_services(request).functional


def has_scope(principal: Principal, required: str) -> bool:
    if principal.scopes & _WILDCARD_SCOPES:
        return True
    return bool(principal.scopes & _SCOPE_ALIASES.get(required, frozenset({required})))


def require_scope(required: str):
    def dependency(principal: Annotated[Principal, Depends(get_principal)]) -> Principal:
        if not has_scope(principal, required):
            raise ForbiddenError(
                "Insufficient scope",
                required_scope=required,
            )
        return principal

    return dependency


def require_permission(required: str):
    def dependency(principal: Annotated[Principal, Depends(get_principal)]) -> Principal:
        if principal.scopes & _WILDCARD_SCOPES:
            return principal
        if required not in principal.scopes:
            raise ForbiddenError("Insufficient permission", required_permission=required)
        return principal

    return dependency


__all__ = [
    "get_admin",
    "get_authenticator",
    "get_datasets",
    "get_datasources",
    "get_evaluation",
    "get_functional",
    "get_gates",
    "get_principal",
    "get_projects",
    "get_reports",
    "get_search",
    "get_services",
    "get_suites",
    "get_targets",
    "get_tenant_context",
    "has_scope",
    "require_permission",
    "require_scope",
]
