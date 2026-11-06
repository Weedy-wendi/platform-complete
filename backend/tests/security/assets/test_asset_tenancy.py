"""Cross-tenant artifact isolation (AST-03)."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine

from app.core.context import TenantContext
from app.core.db import make_session_factory
from app.core.errors import NotFoundError
from app.modules.assets.models import Artifact
from app.modules.assets.service import ArtifactService
from app.modules.assets.storage import build_key
from tests.support.storage import FakeStorage


@pytest.fixture()
def service():
    engine = create_engine("sqlite://")
    Artifact.__table__.create(engine)
    try:
        yield ArtifactService(FakeStorage(), make_session_factory(engine))
    finally:
        engine.dispose()


def _ctx(tenant: str) -> TenantContext:
    return TenantContext(tenant_id=tenant, subject_id="user:1", scopes=frozenset(), trace_id="trace")


def test_cross_tenant_read_and_delete_are_denied(service: ArtifactService) -> None:
    key_a = build_key(
        tenant_id="tenant-a",
        asset_type="dataset",
        asset_id="ds_1",
        version="v1",
        filename="a.csv",
    )
    ref = service.create(_ctx("tenant-a"), key=key_a, data=b"a", mime_type="text/csv")

    with pytest.raises(NotFoundError):
        service.get(_ctx("tenant-b"), ref.artifact_id)
    with pytest.raises(NotFoundError):
        service.delete(_ctx("tenant-b"), ref.artifact_id)
