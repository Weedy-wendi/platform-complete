"""Public identity surface."""

from app.core.context import Principal
from app.modules.identity.api_key import (
    ALLOWED_SCOPES,
    ApiKeyService,
    ApiKeyStore,
    InMemoryApiKeyStore,
    IssuedApiKey,
    SqlApiKeyStore,
)
from app.modules.identity.auth import (
    ApiKeyAuthenticator,
    ApiKeyVerifier,
    JwtAuthenticator,
    SqlTenantStatusChecker,
    TenantStatusChecker,
    build_fastapi_dependency,
    extract_bearer_token,
)
from app.modules.identity.policies import (
    DEFAULT_ROLE_PERMISSIONS,
    IDENTITY_PERMISSIONS,
    AccessPolicy,
    require_any_scope,
    require_permission,
    require_scope,
)
from app.modules.identity.service import IdentityService
from app.modules.identity.views import RoleView, TenantView, UserView

__all__ = [
    "ALLOWED_SCOPES",
    "DEFAULT_ROLE_PERMISSIONS",
    "IDENTITY_PERMISSIONS",
    "AccessPolicy",
    "ApiKeyAuthenticator",
    "ApiKeyService",
    "ApiKeyStore",
    "ApiKeyVerifier",
    "IdentityService",
    "InMemoryApiKeyStore",
    "IssuedApiKey",
    "JwtAuthenticator",
    "Principal",
    "RoleView",
    "SqlApiKeyStore",
    "SqlTenantStatusChecker",
    "TenantStatusChecker",
    "TenantView",
    "UserView",
    "build_fastapi_dependency",
    "extract_bearer_token",
    "require_any_scope",
    "require_permission",
    "require_scope",
]
