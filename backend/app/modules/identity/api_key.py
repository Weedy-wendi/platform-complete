"""API key issuance, verification and revocation.

Keys are high-entropy secrets, so HMAC-SHA256 with a server-side pepper is the
right primitive: constant-time verification without the latency of Argon2.
"""

from __future__ import annotations

import hashlib
import hmac
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.core.clock import utcnow_naive
from app.core.context import Principal
from app.core.errors import NotFoundError, UnauthorizedError
from app.core.ids import new_key_id, new_secret
from app.modules.identity.models import ApiKey
from app.modules.identity.tenant_status import TenantStatusChecker

ALLOWED_SCOPES: frozenset[str] = frozenset(
    {
        "mcp:projects:read",
        "mcp:datasets:read",
        "mcp:eval:read",
        "mcp:eval:read_content",
        "mcp:badcases:read",
        "mcp:gate:read",
    }
)


@dataclass(frozen=True)
class ApiKeyRecord:
    id: int
    tenant_id: str
    key_id: str
    name: str
    secret_hmac: bytes
    scopes: frozenset[str]
    expires_at: datetime | None = None
    revoked_at: datetime | None = None
    created_by: str = "system"


@dataclass(frozen=True)
class IssuedApiKey:
    key_id: str
    raw_key: str
    tenant_id: str
    scopes: frozenset[str]
    expires_at: datetime | None = None


class ApiKeyStore(Protocol):
    def create(self, record: ApiKeyRecord) -> None: ...
    def get_by_key_id(self, key_id: str) -> ApiKeyRecord | None: ...
    def revoke(self, key_id: str, revoked_at: datetime) -> None: ...
    def touch(self, key_id: str, used_at: datetime) -> None: ...


class InMemoryApiKeyStore:
    def __init__(self) -> None:
        self._records: dict[str, ApiKeyRecord] = {}

    def create(self, record: ApiKeyRecord) -> None:
        if record.key_id in self._records:
            raise ValueError("key_id already exists")
        self._records[record.key_id] = record

    def get_by_key_id(self, key_id: str) -> ApiKeyRecord | None:
        return self._records.get(key_id)

    def revoke(self, key_id: str, revoked_at: datetime) -> None:
        record = self._records.get(key_id)
        if record is None:
            return
        self._records[key_id] = ApiKeyRecord(
            id=record.id,
            tenant_id=record.tenant_id,
            key_id=record.key_id,
            name=record.name,
            secret_hmac=record.secret_hmac,
            scopes=record.scopes,
            expires_at=record.expires_at,
            revoked_at=revoked_at,
            created_by=record.created_by,
        )

    def touch(self, key_id: str, used_at: datetime) -> None:
        return None


class SqlApiKeyStore:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def create(self, record: ApiKeyRecord) -> None:
        with self._session_factory() as session:
            session.add(
                ApiKey(
                    tenant_id=record.tenant_id,
                    key_id=record.key_id,
                    name=record.name,
                    secret_hmac=record.secret_hmac,
                    scopes=sorted(record.scopes),
                    expires_at=record.expires_at,
                    revoked_at=record.revoked_at,
                    created_by=record.created_by,
                    created_at=utcnow_naive(),
                )
            )
            session.commit()

    def _to_record(self, row: ApiKey) -> ApiKeyRecord:
        return ApiKeyRecord(
            id=row.id,
            tenant_id=row.tenant_id,
            key_id=row.key_id,
            name=row.name,
            secret_hmac=row.secret_hmac,
            scopes=frozenset(row.scopes or []),
            expires_at=row.expires_at,
            revoked_at=row.revoked_at,
            created_by=row.created_by,
        )

    def get_by_key_id(self, key_id: str) -> ApiKeyRecord | None:
        with self._session_factory() as session:
            row = session.scalar(select(ApiKey).where(ApiKey.key_id == key_id))
            return self._to_record(row) if row else None

    def revoke(self, key_id: str, revoked_at: datetime) -> None:
        with self._session_factory() as session:
            row = session.scalar(select(ApiKey).where(ApiKey.key_id == key_id))
            if row is not None:
                row.revoked_at = revoked_at
                session.commit()

    def touch(self, key_id: str, used_at: datetime) -> None:
        with self._session_factory() as session:
            row = session.scalar(select(ApiKey).where(ApiKey.key_id == key_id))
            if row is not None:
                row.last_used_at = used_at
                session.commit()


class ApiKeyService:
    """Issue and verify API keys.

    Cache entries are keyed by ``key_id`` only after the secret HMAC has been
    verified, so a cache hit can never bypass the secret check.
    """

    def __init__(
        self,
        store: ApiKeyStore,
        *,
        pepper: str,
        key_env: str = "test",
        cache_ttl_seconds: int = 60,
        tenant_status_checker: TenantStatusChecker | None = None,
    ) -> None:
        if not pepper:
            raise ValueError("API key pepper is required")
        if not 0 < cache_ttl_seconds <= 60:
            raise ValueError("cache_ttl_seconds must be between 1 and 60")
        self._store = store
        self._pepper = pepper.encode("utf-8")
        self._key_env = key_env
        self._cache_ttl = cache_ttl_seconds
        self._tenant_status_checker = tenant_status_checker
        self._cache: dict[str, tuple[Principal, bytes, float]] = {}

    @property
    def tenant_status_checker(self) -> TenantStatusChecker | None:
        return self._tenant_status_checker

    def set_tenant_status_checker(self, checker: TenantStatusChecker) -> None:
        self._tenant_status_checker = checker

    def invalidate_tenant_status(self, tenant_id: str) -> None:
        checker = self._tenant_status_checker
        invalidate = getattr(checker, "invalidate", None)
        if callable(invalidate):
            invalidate(tenant_id)

    def _ensure_tenant_active(self, tenant_id: str) -> None:
        checker = self._tenant_status_checker
        if checker is not None and not checker.is_active(tenant_id):
            raise UnauthorizedError("Tenant is disabled")

    def _hmac(self, secret: str) -> bytes:
        return hmac.new(self._pepper, secret.encode("utf-8"), hashlib.sha256).digest()

    def issue(
        self,
        *,
        tenant_id: str,
        name: str,
        scopes: set[str] | frozenset[str],
        expires_at: datetime | None = None,
        created_by: str = "system",
    ) -> IssuedApiKey:
        self._ensure_tenant_active(tenant_id)
        unknown = set(scopes) - ALLOWED_SCOPES
        if unknown:
            raise ValueError(f"Unknown scopes: {', '.join(sorted(unknown))}")
        key_id = new_key_id()
        secret = new_secret()
        raw_key = f"pk_{self._key_env}_{key_id}_{secret}"
        record = ApiKeyRecord(
            id=0,
            tenant_id=tenant_id,
            key_id=key_id,
            name=name,
            secret_hmac=self._hmac(secret),
            scopes=frozenset(scopes),
            expires_at=expires_at,
            created_by=created_by,
        )
        self._store.create(record)
        return IssuedApiKey(
            key_id=key_id,
            raw_key=raw_key,
            tenant_id=tenant_id,
            scopes=record.scopes,
            expires_at=expires_at,
        )

    def verify(self, raw_key: str) -> Principal:
        key_id, secret = self._parse(raw_key)
        digest = self._hmac(secret)
        cached = self._cache.get(key_id)
        now = time.time()
        if cached and cached[2] > now and hmac.compare_digest(cached[1], digest):
            self._ensure_tenant_active(cached[0].tenant_id)
            return cached[0]

        record = self._store.get_by_key_id(key_id)
        if record is None:
            raise UnauthorizedError("Invalid API key")
        if not hmac.compare_digest(record.secret_hmac, digest):
            raise UnauthorizedError("Invalid API key")
        if record.revoked_at is not None:
            raise UnauthorizedError("API key revoked")
        if record.expires_at is not None and record.expires_at <= utcnow_naive():
            raise UnauthorizedError("API key expired")
        self._ensure_tenant_active(record.tenant_id)

        principal = Principal(
            tenant_id=record.tenant_id,
            subject=f"api_key:{record.key_id}",
            scopes=record.scopes,
            auth_method="api_key",
            expires_at=record.expires_at,
            client_id=record.key_id,
            api_key_id=record.id,
        )
        self._cache[key_id] = (principal, digest, now + self._cache_ttl)
        return principal

    def _parse(self, raw_key: str) -> tuple[str, str]:
        if not raw_key:
            raise UnauthorizedError("Missing API key")
        parts = raw_key.split("_", 3)
        if len(parts) != 4 or parts[0] != "pk" or not parts[2] or not parts[3]:
            raise UnauthorizedError("Malformed API key")
        return parts[2], parts[3]

    def get_record(self, key_id: str) -> ApiKeyRecord | None:
        return self._store.get_by_key_id(key_id)

    def revoke(self, key_id: str, *, tenant_id: str | None = None) -> None:
        record = self._store.get_by_key_id(key_id)
        if record is None:
            if tenant_id is not None:
                raise NotFoundError("API key not found")
            return
        if tenant_id is not None and record.tenant_id != tenant_id:
            raise NotFoundError("API key not found")
        self._store.revoke(key_id, utcnow_naive())
        self._cache.pop(key_id, None)

    def rotate(self, key_id: str, *, tenant_id: str | None = None, created_by: str = "system") -> IssuedApiKey:
        record = self._store.get_by_key_id(key_id)
        if record is None or record.revoked_at is not None:
            raise NotFoundError("API key not found")
        if tenant_id is not None and record.tenant_id != tenant_id:
            raise NotFoundError("API key not found")
        self.revoke(key_id, tenant_id=tenant_id)
        return self.issue(
            tenant_id=record.tenant_id,
            name=record.name,
            scopes=record.scopes,
            expires_at=record.expires_at,
            created_by=created_by,
        )
