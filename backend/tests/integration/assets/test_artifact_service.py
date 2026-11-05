"""Artifact metadata/service tests (AST-02/03)."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine

from app.core.context import TenantContext
from app.core.db import make_session_factory
from app.core.errors import InvalidArgumentError, NotFoundError
from app.modules.assets.models import Artifact
from app.modules.assets.service import ArtifactService
from app.modules.assets.storage import build_key
from tests.support.storage import FakeStorage


@pytest.fixture()
def factory():
    engine = create_engine("sqlite://")
    Artifact.__table__.create(engine)
    try:
        yield make_session_factory(engine)
    finally:
        engine.dispose()


@pytest.fixture()
def storage() -> FakeStorage:
    return FakeStorage()


@pytest.fixture()
def service(storage, factory) -> ArtifactService:
    return ArtifactService(storage, factory)


@pytest.fixture()
def ctx() -> TenantContext:
    return TenantContext(tenant_id="tenant-a", subject_id="user:1", scopes=frozenset(), trace_id="trace-1")


def _key(tenant: str = "tenant-a") -> str:
    return build_key(
        tenant_id=tenant,
        asset_type="dataset",
        asset_id="ds_1",
        version="v1",
        filename="samples.csv",
    )


def test_create_get_and_checksum(service: ArtifactService, storage: FakeStorage, ctx) -> None:
    ref = service.create(ctx, key=_key(), data=b"a,b\n1,2\n", mime_type="text/csv")
    assert ref.tenant_id == "tenant-a"
    assert ref.size_bytes == 8
    assert len(ref.sha256) == 64
    assert service.get(ctx, ref.artifact_id).s3_key == _key()
    assert service.get_bytes(ctx, ref.artifact_id) == b"a,b\n1,2\n"
    assert storage.objects[_key()][0] == b"a,b\n1,2\n"


def test_presign_respects_ttl(service: ArtifactService, ctx) -> None:
    ref = service.create(ctx, key=_key(), data=b"x", mime_type="text/plain")
    assert "ttl=900" in service.presign_get(ctx, ref.artifact_id)
    assert "ttl=60" in service.presign_get(ctx, ref.artifact_id, ttl_seconds=60)
    with pytest.raises(InvalidArgumentError):
        service.presign_get(ctx, ref.artifact_id, ttl_seconds=901)


def test_checksum_mismatch_is_rejected(service: ArtifactService, storage: FakeStorage, ctx) -> None:
    ref = service.create(ctx, key=_key(), data=b"abc", mime_type="text/plain")
    storage.tamper_reads = True
    with pytest.raises(InvalidArgumentError):
        service.get_bytes(ctx, ref.artifact_id)


def test_wrong_tenant_prefix_is_rejected(service: ArtifactService, ctx) -> None:
    with pytest.raises(InvalidArgumentError):
        service.create(ctx, key=_key("tenant-b"), data=b"x", mime_type="text/plain")


def test_cross_tenant_read_is_404(service: ArtifactService, ctx) -> None:
    ref = service.create(ctx, key=_key(), data=b"x", mime_type="text/plain")
    other = TenantContext(tenant_id="tenant-b", subject_id="user:2", scopes=frozenset(), trace_id="trace-2")
    with pytest.raises(NotFoundError):
        service.get(other, ref.artifact_id)
    with pytest.raises(NotFoundError):
        service.presign_get(other, ref.artifact_id)
    with pytest.raises(NotFoundError):
        service.get_bytes(other, ref.artifact_id)


def test_duplicate_key_is_rejected_without_overwriting(service: ArtifactService, storage: FakeStorage, ctx) -> None:
    key = _key()
    service.create(ctx, key=key, data=b"first", mime_type="text/plain")
    with pytest.raises(InvalidArgumentError):
        service.create(ctx, key=key, data=b"second", mime_type="text/plain")
    assert storage.objects[key][0] == b"first"


def test_delete_removes_metadata_and_object(service: ArtifactService, storage: FakeStorage, ctx) -> None:
    ref = service.create(ctx, key=_key(), data=b"x", mime_type="text/plain")
    service.delete(ctx, ref.artifact_id)
    assert ref.s3_key not in storage.objects
    with pytest.raises(NotFoundError):
        service.get(ctx, ref.artifact_id)
