"""Storage adapter contract tests (AST-01/02/04/05)."""

from __future__ import annotations

import pytest

from app.core.errors import InvalidArgumentError, NotFoundError, UpstreamUnavailableError
from app.modules.assets.local import LocalStorage
from app.modules.assets.s3 import MinioStorage, OssStorage, S3Storage
from app.modules.assets.storage import build_key, validate_ttl
from tests.support.storage import FakeS3Client, FakeStorage


@pytest.fixture(params=["local", "fake", "oss", "minio"])
def storage(request, tmp_path):
    if request.param == "local":
        return LocalStorage(tmp_path)
    if request.param == "fake":
        return FakeStorage()
    client = FakeS3Client()
    if request.param == "oss":
        return OssStorage(client, bucket="contract")
    return MinioStorage(client, bucket="contract")


def test_put_get_delete_round_trip(storage, tmp_path) -> None:
    key = build_key(
        tenant_id="tenant-a",
        asset_type="dataset",
        asset_id="ds_1",
        version="v1",
        filename="samples.csv",
    )
    digest = storage.put(key, b"a,b\n1,2\n", content_type="text/csv")
    assert len(digest) == 64
    assert storage.get(key) == b"a,b\n1,2\n"
    storage.delete(key)
    with pytest.raises(NotFoundError):
        storage.get(key)


def test_presign_is_bounded(storage) -> None:
    url = storage.presign_get("tenant/tenant-a/dataset/ds_1/v1/a.csv", ttl_seconds=900)
    assert "900" in url or "expires" in url
    with pytest.raises(InvalidArgumentError):
        storage.presign_get("tenant/tenant-a/dataset/ds_1/v1/a.csv", ttl_seconds=901)
    with pytest.raises(InvalidArgumentError):
        validate_ttl(0)


def test_build_key_rejects_traversal() -> None:
    with pytest.raises(InvalidArgumentError):
        build_key(
            tenant_id="tenant-a",
            asset_type="dataset",
            asset_id="ds_1",
            version="v1",
            filename="../../etc/passwd",
        )


def test_s3_maps_4xx_and_5xx() -> None:
    client = FakeS3Client()
    storage = S3Storage(client, bucket="contract")
    client.fail_status = 403
    with pytest.raises(InvalidArgumentError):
        storage.put("tenant/tenant-a/dataset/ds_1/v1/a.csv", b"x", content_type="text/csv")
    client.fail_status = 503
    with pytest.raises(UpstreamUnavailableError):
        storage.put("tenant/tenant-a/dataset/ds_1/v1/a.csv", b"x", content_type="text/csv")
