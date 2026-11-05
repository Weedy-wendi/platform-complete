"""OAuth 2.1 Resource Server support (reserved).

The provider is intentionally isolated behind the same SPI as API keys. When an
IdP is available, configure iss/aud/jwks and switch MCP_AUTH_MODE=oauth; tool
handlers do not change.
"""

from __future__ import annotations

from datetime import UTC, datetime

import jwt

from app.core.context import Principal
from app.mcp.auth.base import AuthError


class OAuthResourceServerProvider:
    def __init__(self, *, issuer: str, audience: str, jwks_url: str) -> None:
        if not issuer or not audience or not jwks_url:
            raise ValueError("OAuth issuer, audience and jwks_url are required")
        self._issuer = issuer
        self._audience = audience
        self._jwks = jwt.PyJWKClient(jwks_url)

    async def authenticate(self, authorization: str | None) -> Principal:
        if not authorization:
            raise AuthError("Missing Authorization header", reason="missing")
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not token.strip():
            raise AuthError("Malformed Authorization header", reason="malformed")
        try:
            signing_key = self._jwks.get_signing_key_from_jwt(token)
            claims = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256", "ES256", "EdDSA"],
                audience=self._audience,
                issuer=self._issuer,
            )
        except jwt.PyJWTError as exc:
            raise AuthError("Invalid OAuth token", reason="invalid_token") from exc

        tenant_id = claims.get("tenant_id") or claims.get("tenant")
        if not tenant_id:
            raise AuthError("Token is missing tenant_id", status_code=403, code="FORBIDDEN", reason="missing_tenant")
        scopes = claims.get("scope") or claims.get("scp") or ""
        scope_set = frozenset(scopes.split()) if isinstance(scopes, str) else frozenset(scopes)
        exp = claims.get("exp")
        return Principal(
            tenant_id=str(tenant_id),
            subject=str(claims.get("sub", "unknown")),
            scopes=scope_set,
            auth_method="oauth",
            expires_at=datetime.fromtimestamp(exp, tz=UTC) if exp else None,
            client_id=claims.get("client_id"),
        )
