import pytest

from app.core.errors import UnauthorizedError
from app.modules.identity.api_key import ALLOWED_SCOPES, ApiKeyService, InMemoryApiKeyStore


@pytest.fixture()
def service() -> ApiKeyService:
    return ApiKeyService(InMemoryApiKeyStore(), pepper="pepper", key_env="test")


def test_issue_and_verify(service: ApiKeyService) -> None:
    issued = service.issue(tenant_id="tenant-a", name="key", scopes={"mcp:projects:read"})
    assert issued.raw_key.startswith("pk_test_")
    principal = service.verify(issued.raw_key)
    assert principal.tenant_id == "tenant-a"
    assert principal.scopes == frozenset({"mcp:projects:read"})


def test_secret_is_not_stored_in_plaintext(service: ApiKeyService) -> None:
    issued = service.issue(tenant_id="tenant-a", name="key", scopes={"mcp:projects:read"})
    record = service._store.get_by_key_id(issued.key_id)  # type: ignore[attr-defined]
    assert record is not None
    assert issued.raw_key.split("_", 3)[3].encode() not in record.secret_hmac


def test_revoke_invalidates_cached_key(service: ApiKeyService) -> None:
    issued = service.issue(tenant_id="tenant-a", name="key", scopes={"mcp:projects:read"})
    assert service.verify(issued.raw_key).tenant_id == "tenant-a"
    service.revoke(issued.key_id)
    with pytest.raises(UnauthorizedError):
        service.verify(issued.raw_key)


def test_expired_key_is_rejected(service: ApiKeyService) -> None:
    from app.core.clock import utcnow_naive

    issued = service.issue(
        tenant_id="tenant-a",
        name="key",
        scopes={"mcp:projects:read"},
        expires_at=utcnow_naive(),
    )
    with pytest.raises(UnauthorizedError):
        service.verify(issued.raw_key)


def test_bad_key_is_rejected(service: ApiKeyService) -> None:
    with pytest.raises(UnauthorizedError):
        service.verify("not-a-key")


def test_revocation_takes_effect_within_cache_ttl(service: ApiKeyService, monkeypatch) -> None:
    import app.modules.identity.api_key as api_key_module

    issued = service.issue(tenant_id="tenant-a", name="ttl", scopes={"mcp:projects:read"})
    assert service.verify(issued.raw_key).tenant_id == "tenant-a"

    # Simulate a revocation that happened after the cache was populated but
    # before the entry expired (e.g. another process revoked the key).
    service._store.revoke(issued.key_id, api_key_module.utcnow_naive())  # type: ignore[attr-defined]

    assert service.verify(issued.raw_key).tenant_id == "tenant-a"

    real_time = api_key_module.time.time
    monkeypatch.setattr(api_key_module.time, "time", lambda: real_time() + 61)
    with pytest.raises(UnauthorizedError):
        service.verify(issued.raw_key)


def test_unknown_scope_is_rejected(service: ApiKeyService) -> None:
    with pytest.raises(ValueError):
        service.issue(tenant_id="tenant-a", name="key", scopes={"mcp:unknown:read"})


def test_allowed_scopes_are_read_only() -> None:
    assert all(scope.endswith(":read") or scope == "mcp:eval:read_content" for scope in ALLOWED_SCOPES)


def test_rotate_revokes_old_and_issues_new(service: ApiKeyService) -> None:
    issued = service.issue(tenant_id="tenant-a", name="key", scopes={"mcp:projects:read"})
    replacement = service.rotate(issued.key_id, tenant_id="tenant-a")
    assert replacement.key_id != issued.key_id
    assert replacement.tenant_id == "tenant-a"
    assert replacement.scopes == frozenset({"mcp:projects:read"})
    with pytest.raises(UnauthorizedError):
        service.verify(issued.raw_key)
    assert service.verify(replacement.raw_key).tenant_id == "tenant-a"


def test_revoke_is_tenant_scoped(service: ApiKeyService) -> None:
    from app.core.errors import NotFoundError

    issued = service.issue(tenant_id="tenant-a", name="key", scopes={"mcp:projects:read"})
    with pytest.raises(NotFoundError):
        service.revoke(issued.key_id, tenant_id="tenant-b")
    assert service.verify(issued.raw_key).tenant_id == "tenant-a"


def test_cache_ttl_must_be_between_1_and_60() -> None:
    for ttl in (0, -1, 61, 3600):
        with pytest.raises(ValueError):
            ApiKeyService(InMemoryApiKeyStore(), pepper="pepper", cache_ttl_seconds=ttl)
    configured = ApiKeyService(InMemoryApiKeyStore(), pepper="pepper", cache_ttl_seconds=60)
    assert configured._cache_ttl == 60  # type: ignore[attr-defined]
